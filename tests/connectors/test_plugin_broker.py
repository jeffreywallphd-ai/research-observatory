"""No live traffic: signed routing, current authority, SSRF and response bounds."""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx2
from jsonschema import Draft202012Validator
from nacl.signing import SigningKey

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))

from research_observatory_core.connectors.plugin_broker import (  # noqa: E402
    PluginBrokerCall,
    PluginBrokerProblem,
    PluginBrokerRates,
    PluginNetworkBroker,
    PluginPublicNetworkBackend,
    PluginRepositoryMetadata,
    _PluginHTTPTransport,
)
from research_observatory_core.connectors.plugin_manifest import (  # noqa: E402
    PluginInvocationRequest,
    PluginProjectGrant,
    authorize_plugin_invocation,
    verify_plugin_package,
)

PROJECT = "0190a000-0000-7000-8000-000000000040"
INVOCATION = "0190a000-0000-7000-8000-000000000042"
ENTRY = "plugin/connector.py"
PAYLOAD = b"# synthetic package, never executed\n"
DESTINATION = {
    "scheme": "https",
    "host": "repository.example.invalid",
    "port": 443,
    "pathTemplate": "/v1/records/{identifier}",
}
SECRET = "synthetic-token-private"


class BytesStream(httpx2.AsyncByteStream):
    def __init__(self, body: bytes):
        self.body = body

    async def __aiter__(self):
        for start in range(0, len(self.body), 8192):
            yield self.body[start : start + 8192]


def streamed(response: httpx2.Response) -> httpx2.Response:
    return httpx2.Response(response.status_code, headers=response.headers, stream=BytesStream(response.content))


def fixture(*, authentication: bool = False, destination: dict | None = None, destinations: list[dict] | None = None):
    key = SigningKey(b"\x03" * 32)
    target = destination or DESTINATION
    targets = destinations or [target]
    manifest = {
        "schemaVersion": "1.0",
        "pluginId": "fixture.repository",
        "pluginVersion": "1.0.0",
        "sdkVersion": "1.0.0",
        "requiredFeatures": ["source-assertions-v1", "brokered-requests-v1"],
        "publisherKeyId": "synthetic-key",
        "sourceIdentity": {"sourceId": "plugin.fixture.repository", "displayName": "Synthetic repository"},
        "authentication": {"mode": "broker-scoped" if authentication else "none"},
        "terms": {"status": "not-reported"},
        "rateLimits": {"maxRequestsPerSecond": 1, "maxConcurrent": 1},
        "entryPoint": ENTRY,
        "files": [{"path": ENTRY, "sha256": "sha256:" + hashlib.sha256(PAYLOAD).hexdigest()}],
        "operations": ["lookup", "search", "references", "citations", "open-access-locations", "repository-metadata"],
        "destinations": targets,
        "credentialScopes": ["repository-token"] if authentication else [],
        "dataClasses": ["public-metadata"],
        "rightsBehavior": "source-assertions-only",
        "resourceProfile": {"committedMemoryMiB": 256, "maxJobsPerProject": 1, "wallTimeSeconds": 60},
        "permissions": ["provider-network", "credential-broker"] if authentication else ["provider-network"],
    }
    raw = json.dumps(manifest, separators=(",", ":")).encode()
    package = verify_plugin_package(
        raw, key.sign(raw).signature, {ENTRY: PAYLOAD}, {"synthetic-key": bytes(key.verify_key)}
    )
    grant = PluginProjectGrant.model_validate(
        {
            "projectId": PROJECT,
            "pluginId": manifest["pluginId"],
            "pluginVersion": manifest["pluginVersion"],
            "packageSha256": package.package_sha256,
            "manifestSha256": package.manifest_sha256,
            "publisherKeyId": manifest["publisherKeyId"],
            "permissions": manifest["permissions"],
            "destinations": targets,
            "revision": 1,
        }
    )
    return package, grant


def plan_for(package, grant, operation="lookup", destination_index=0):
    return authorize_plugin_invocation(
        package,
        grant,
        PluginInvocationRequest.model_validate(
            {
                "projectId": PROJECT,
                "invocationId": INVOCATION,
                "scientificRequestSha256": "sha256:" + "a" * 64,
                "operation": operation,
                "destination": package.manifest.destinations[destination_index].model_dump(mode="json", by_alias=True),
            }
        ),
    )


def request_for(plan):
    return PluginInvocationRequest(
        project_id=plan.project_id,
        invocation_id=plan.invocation_id,
        scientific_request_sha256=plan.scientific_request_sha256,
        operation=plan.operation,
        destination=plan.destination,
    )


class PluginBrokerTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_signed_route_and_current_scientific_decision(self):
        package, grant = fixture()
        plan = plan_for(package, grant)
        seen = []
        audits = []

        def recheck(current, call):
            seen.append((current.request_sha256, call.identifier))
            if call.identifier != "10.1234/example":
                raise PluginBrokerProblem("policy-denied")

        def respond(request):
            self.assertEqual("repository.example.invalid", request.url.host)
            self.assertEqual("/v1/records/10.1234%2Fexample", request.url.raw_path.decode())
            self.assertEqual("GET", request.method)
            return streamed(httpx2.Response(200, json={"id": "10.1234/example"}))

        broker = PluginNetworkBroker(
            package=package,
            current_grant=lambda *_: grant,
            current_request=lambda *_: request_for(plan),
            current_credential_origin=lambda *_: None,
            rates=PluginBrokerRates(),
            recheck=recheck,
            audit_denial=audits.append,
            transport_factory=lambda *_: httpx2.MockTransport(respond),
            sleep=AsyncMock(),
        )
        result = await broker.fetch(plan, PluginBrokerCall(operation="lookup", identifier="10.1234/example"))
        self.assertEqual({"id": "10.1234/example"}, json.loads(result.body))
        self.assertGreaterEqual(len(seen), 1)
        with self.assertRaises(PluginBrokerProblem):
            await broker.fetch(plan, PluginBrokerCall(operation="lookup", identifier="other"))
        self.assertGreaterEqual(len(seen), 2)
        self.assertEqual(["policy-denied"], audits)

    async def test_stale_grant_forged_plan_missing_policy_and_operation_mismatch_deny_before_transport(self):
        package, grant = fixture()
        plan = plan_for(package, grant)
        network = AsyncMock()
        network.handle_async_request = AsyncMock()
        call = PluginBrokerCall(operation="lookup", identifier="paper")
        for current_grant, recheck, chosen_plan, chosen_call in (
            (lambda *_: grant.model_copy(update={"revision": 2}), lambda *_: None, plan, call),
            (lambda *_: grant, None, plan, call),
            (
                lambda *_: grant,
                lambda *_: None,
                plan.model_copy(update={"project_id": "0190a000-0000-7000-8000-000000000041"}),
                call,
            ),
            (lambda *_: grant, lambda *_: None, plan, PluginBrokerCall(operation="search", query="test", page_size=10)),
            (
                lambda *_: grant,
                lambda *_: None,
                plan.model_copy(update={"scientific_request_sha256": "sha256:" + "b" * 64}),
                call,
            ),
        ):
            broker = PluginNetworkBroker(
                package=package,
                current_grant=current_grant,
                current_request=lambda *_: request_for(plan),
                current_credential_origin=lambda *_: None,
                rates=PluginBrokerRates(),
                recheck=recheck,
                audit_denial=lambda _: None,
                transport_factory=lambda *_: network,
            )
            with (
                self.subTest(case=(current_grant, recheck, chosen_call.operation)),
                self.assertRaises(PluginBrokerProblem),
            ):
                await broker.fetch(chosen_plan, chosen_call)
        network.handle_async_request.assert_not_called()

    async def test_operation_specific_shape_blocks_url_header_and_repository_escape(self):
        for kwargs in (
            {"operation": "lookup", "identifier": "paper", "url": "http://127.0.0.1"},
            {"operation": "lookup", "identifier": "paper", "query": "secret"},
            {"operation": "search", "query": "topic", "identifier": "paper", "page_size": 10},
            {"operation": "repository-metadata", "repository_id": "https://127.0.0.1/private"},
            {"operation": "repository-metadata", "repository_id": "../../secret"},
            {"operation": "lookup", "identifier": ".."},
            {"operation": "search", "query": "topic", "page_size": 1001},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises((ValueError, PluginBrokerProblem)):
                PluginBrokerCall(**kwargs)

    async def test_redirects_and_unbounded_or_non_json_results_never_publish_body(self):
        package, grant = fixture()
        plan = plan_for(package, grant)
        for response in (
            httpx2.Response(302, headers={"Location": "http://127.0.0.1/private"}),
            httpx2.Response(
                200, headers={"content-type": "application/json"}, stream=BytesStream(b"x" * (10 * 1024 * 1024 + 1))
            ),
            httpx2.Response(200, headers={"content-type": "text/plain"}, stream=BytesStream(b"private")),
        ):
            broker = PluginNetworkBroker(
                package=package,
                current_grant=lambda *_: grant,
                current_request=lambda *_: request_for(plan),
                current_credential_origin=lambda *_: None,
                rates=PluginBrokerRates(),
                recheck=lambda *_: None,
                audit_denial=lambda _: None,
                transport_factory=lambda *_, response=response: httpx2.MockTransport(lambda _: response),
            )
            with self.subTest(status=response.status_code), self.assertRaises(PluginBrokerProblem):
                await broker.fetch(plan, PluginBrokerCall(operation="lookup", identifier="paper"))

    async def test_secret_stays_core_side_and_echo_is_redacted(self):
        package, grant = fixture(authentication=True)
        plan = plan_for(package, grant)
        lease_count = 0

        @contextmanager
        def lease(scope, current):
            nonlocal lease_count
            lease_count += 1
            self.assertEqual("repository-token", scope)
            self.assertEqual(plan, current)
            yield SECRET

        def respond(request):
            self.assertEqual("Bearer " + SECRET, request.headers["authorization"])
            return streamed(httpx2.Response(200, json={"future": SECRET, "safe": "metadata"}))

        broker = PluginNetworkBroker(
            package=package,
            current_grant=lambda *_: grant,
            current_request=lambda *_: request_for(plan),
            current_credential_origin=lambda *_: ("https", "repository.example.invalid", 443),
            rates=PluginBrokerRates(),
            recheck=lambda *_: None,
            audit_denial=lambda _: None,
            lease_secret=lease,
            transport_factory=lambda *_: httpx2.MockTransport(respond),
        )
        result = await broker.fetch(
            plan, PluginBrokerCall(operation="lookup", identifier="paper", credential_scope="repository-token")
        )
        self.assertTrue(result.redacted)
        self.assertEqual(1, lease_count)
        self.assertNotIn(SECRET.encode(), result.body)
        self.assertEqual("metadata", json.loads(result.body)["safe"])
        denied = PluginNetworkBroker(
            package=package,
            current_grant=lambda *_: grant,
            current_request=lambda *_: request_for(plan),
            current_credential_origin=lambda *_: None,
            rates=PluginBrokerRates(),
            recheck=lambda *_: None,
            audit_denial=lambda _: None,
            transport_factory=lambda *_: httpx2.MockTransport(respond),
        )
        with self.assertRaises(PluginBrokerProblem):
            await denied.fetch(
                plan, PluginBrokerCall(operation="lookup", identifier="paper", credential_scope="repository-token")
            )

    async def test_all_resolved_addresses_public_and_tcp_uses_checked_numeric_ip(self):
        backend = AsyncMock()
        network = PluginPublicNetworkBackend("repository.example.invalid", 443, backend)
        for answers in (("127.0.0.1",), ("8.8.8.8", "10.0.0.2"), ("::ffff:127.0.0.1",), ("169.254.169.254",)):
            values = [(0, 0, 0, "", (address, 443)) for address in answers]
            with (
                patch("asyncio.BaseEventLoop.getaddrinfo", new=AsyncMock(return_value=values)),
                self.subTest(answers=answers),
                self.assertRaises(PluginBrokerProblem),
            ):
                await network.connect_tcp("repository.example.invalid", 443, timeout=2)
            backend.connect_tcp.assert_not_called()
        values = [(0, 0, 0, "", ("8.8.8.8", 443))]
        with patch("asyncio.BaseEventLoop.getaddrinfo", new=AsyncMock(return_value=values)) as resolve:
            await network.connect_tcp("repository.example.invalid", 443, timeout=2)
        resolve.assert_awaited_once()
        self.assertEqual("8.8.8.8", backend.connect_tcp.await_args.args[0])
        with self.assertRaises(PluginBrokerProblem):
            await network.connect_tcp("other.example.invalid", 443)

    async def test_rate_wait_rechecks_revoked_grant_before_retry(self):
        package, grant = fixture()
        plan = plan_for(package, grant)
        now = [100.0]
        current = [grant]
        sent = []

        async def wait(seconds):
            now[0] += seconds
            current[0] = None

        def respond(request):
            sent.append(request.url.path)
            return streamed(httpx2.Response(200, json={"ok": True}))

        broker = PluginNetworkBroker(
            package=package,
            current_grant=lambda *_: current[0],
            current_request=lambda *_: request_for(plan),
            current_credential_origin=lambda *_: None,
            rates=PluginBrokerRates(),
            recheck=lambda *_: None,
            audit_denial=lambda _: None,
            transport_factory=lambda *_: httpx2.MockTransport(respond),
            clock=lambda: now[0],
            sleep=wait,
        )
        call = PluginBrokerCall(operation="lookup", identifier="paper")
        await broker.fetch(plan, call)
        with self.assertRaises(PluginBrokerProblem) as denied:
            await broker.fetch(plan, call)
        self.assertEqual("policy-denied", denied.exception.code)
        self.assertEqual(1, len(sent))

    async def test_transport_itself_rejects_changed_host_path_method_and_scheme(self):
        package, _ = fixture()
        destination = package.manifest.destinations[0]
        transport = _PluginHTTPTransport(destination, "/v1/records/paper")
        try:
            for method, url, body in (
                ("GET", "http://repository.example.invalid/v1/records/paper", b""),
                ("GET", "https://other.example.invalid/v1/records/paper", b""),
                ("GET", "https://repository.example.invalid/v1/records/other", b""),
                ("POST", "https://repository.example.invalid/v1/records/paper", b"{}"),
                ("GET", "https://name:password@repository.example.invalid/v1/records/paper", b""),
            ):
                with patch.object(transport._pool, "handle_async_request", new=AsyncMock()) as network:
                    with self.subTest(method=method, url=url), self.assertRaises(PluginBrokerProblem):
                        await transport.handle_async_request(httpx2.Request(method, url, content=body))
                    network.assert_not_called()
        finally:
            await transport.aclose()

    async def test_repository_metadata_requires_exact_public_assertion_shape(self):
        destination = {
            "scheme": "https",
            "host": "repository.example.invalid",
            "port": 443,
            "pathTemplate": "/v1/repositories/{repository_id}",
        }
        package, grant = fixture(destination=destination)
        plan = plan_for(package, grant, "repository-metadata")
        call = PluginBrokerCall(operation="repository-metadata", repository_id="archive-01")

        def broker_for(value):
            return PluginNetworkBroker(
                package=package,
                current_grant=lambda *_: grant,
                current_request=lambda *_: request_for(plan),
                current_credential_origin=lambda *_: None,
                rates=PluginBrokerRates(),
                recheck=lambda *_: None,
                audit_denial=lambda _: None,
                transport_factory=lambda *_: httpx2.MockTransport(lambda _: streamed(httpx2.Response(200, json=value))),
            )

        valid = {"repositoryId": "archive-01", "displayName": "Public archive", "description": "Metadata only"}
        result = await broker_for(valid).fetch(plan, call)
        self.assertEqual(valid, json.loads(result.body))
        for invalid in (
            valid | {"repositoryId": "other"},
            valid | {"downloadUrl": "http://127.0.0.1/private"},
            valid | {"displayName": " "},
            valid | {"description": "private\x00data"},
            [valid],
        ):
            with self.subTest(invalid=invalid), self.assertRaises(PluginBrokerProblem) as denied:
                await broker_for(invalid).fetch(plan, call)
            self.assertEqual("incompatible-response", denied.exception.code)

    async def test_secret_scope_is_bound_to_one_core_owned_origin_even_when_two_are_signed(self):
        second = DESTINATION | {"host": "other.example.invalid"}
        package, grant = fixture(authentication=True, destinations=[DESTINATION, second])
        plan = plan_for(package, grant, destination_index=1)
        leases = []
        audits = []

        @contextmanager
        def lease(*_):
            leases.append(True)
            yield SECRET

        broker = PluginNetworkBroker(
            package=package,
            current_grant=lambda *_: grant,
            current_request=lambda *_: request_for(plan),
            current_credential_origin=lambda *_: ("https", DESTINATION["host"], 443),
            rates=PluginBrokerRates(),
            recheck=lambda *_: None,
            audit_denial=audits.append,
            lease_secret=lease,
            transport_factory=lambda *_: self.fail("network reached"),
        )
        with self.assertRaises(PluginBrokerProblem) as denied:
            await broker.fetch(
                plan, PluginBrokerCall(operation="lookup", identifier="paper", credential_scope="repository-token")
            )
        self.assertEqual("credential-denied", denied.exception.code)
        self.assertEqual(["credential-denied"], audits)
        self.assertEqual([], leases)

    async def test_two_broker_instances_share_plugin_rate_budget(self):
        package, grant = fixture()
        plan = plan_for(package, grant)
        rates = PluginBrokerRates()
        now = [100.0]
        waits = []

        async def wait(seconds):
            waits.append(seconds)
            now[0] += seconds

        def make_broker():
            return PluginNetworkBroker(
                package=package,
                current_grant=lambda *_: grant,
                current_request=lambda *_: request_for(plan),
                current_credential_origin=lambda *_: None,
                rates=rates,
                recheck=lambda *_: None,
                audit_denial=lambda _: None,
                transport_factory=lambda *_: httpx2.MockTransport(
                    lambda _: streamed(httpx2.Response(200, json={"ok": True}))
                ),
                clock=lambda: now[0],
                sleep=wait,
            )

        call = PluginBrokerCall(operation="lookup", identifier="paper")
        await make_broker().fetch(plan, call)
        await make_broker().fetch(plan, call)
        self.assertEqual([1.0], waits)

    async def test_percent_encoded_target_limit_deny_precedes_transport(self):
        destination = DESTINATION | {"pathTemplate": "/v1/search"}
        package, grant = fixture(destination=destination)
        plan = plan_for(package, grant, "search")
        audits = []
        broker = PluginNetworkBroker(
            package=package,
            current_grant=lambda *_: grant,
            current_request=lambda *_: request_for(plan),
            current_credential_origin=lambda *_: None,
            rates=PluginBrokerRates(),
            recheck=lambda *_: None,
            audit_denial=audits.append,
            transport_factory=lambda *_: self.fail("transport constructed"),
        )
        with self.assertRaises(PluginBrokerProblem) as denied:
            await broker.fetch(plan, PluginBrokerCall(operation="search", query="漢" * 4096))
        self.assertEqual("route-denied", denied.exception.code)
        self.assertEqual(["route-denied"], audits)

    async def test_async_or_failed_audit_and_transport_construction_fail_closed(self):
        package, grant = fixture()
        plan = plan_for(package, grant)

        async def async_audit(_):
            pass

        common = dict(
            package=package,
            current_grant=lambda *_: grant,
            current_request=lambda *_: request_for(plan),
            current_credential_origin=lambda *_: None,
            rates=PluginBrokerRates(),
            recheck=None,
        )
        with self.assertRaises(ValueError):
            PluginNetworkBroker(**common, audit_denial=async_audit)

        def returning_awaitable(_):
            return async_audit("policy-denied")

        broker = PluginNetworkBroker(**common, audit_denial=returning_awaitable)
        with self.assertRaises(PluginBrokerProblem) as denied:
            await broker.fetch(plan, PluginBrokerCall(operation="lookup", identifier="paper"))
        self.assertEqual("audit-unavailable", denied.exception.code)

        audits = []

        def broken_transport(*_):
            raise RuntimeError("synthetic-private-sentinel")

        broker = PluginNetworkBroker(
            **(common | {"recheck": lambda *_: None}),
            audit_denial=audits.append,
            transport_factory=broken_transport,
        )
        with self.assertRaises(PluginBrokerProblem) as denied:
            await broker.fetch(plan, PluginBrokerCall(operation="lookup", identifier="paper"))
        self.assertEqual("provider-unavailable", denied.exception.code)
        self.assertEqual(["provider-unavailable"], audits)
        self.assertNotIn("synthetic-private-sentinel", str(denied.exception))

    def test_published_broker_call_and_repository_schema_match_runtime(self):
        fixtures = (
            (
                "connector-plugin-broker-call.schema.json",
                PluginBrokerCall,
                {"operation": "lookup", "identifier": "paper"},
            ),
            (
                "connector-plugin-repository-metadata.schema.json",
                PluginRepositoryMetadata,
                {"repositoryId": "archive-01", "displayName": "Public archive"},
            ),
        )
        for filename, model, valid in fixtures:
            schema = json.loads((REPO / "packages/contracts/connectors" / filename).read_text("utf-8"))
            with self.subTest(filename=filename):
                Draft202012Validator.check_schema(schema)
                self.assertEqual([], list(Draft202012Validator(schema).iter_errors(valid)))
                self.assertEqual(
                    [],
                    list(
                        Draft202012Validator(schema).iter_errors(
                            model.model_validate(valid).model_dump(mode="json", by_alias=True, exclude_none=True)
                        )
                    ),
                )
                self.assertNotEqual(
                    [], list(Draft202012Validator(schema).iter_errors(valid | {"url": "http://127.0.0.1"}))
                )


if __name__ == "__main__":
    unittest.main()
