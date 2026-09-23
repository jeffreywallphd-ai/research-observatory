"""Synthetic portable connector boundaries; no provider calls or secret access."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))
sys.path.insert(0, str(REPO / "tools"))

from research_observatory_core.connectors.contracts import (  # noqa: E402
    ConnectorCapabilities,
    ConnectorError,
    ConnectorRequest,
    ConnectorResultPage,
)
from research_observatory_core.ports.connectors import ConnectorAdapter, ConnectorFailure  # noqa: E402


def page_document() -> dict[str, Any]:
    return json.loads((REPO / "tests/fixtures/scholarly-metadata/connector-page.v1.json").read_text("utf-8"))


def cursor_document(request: ConnectorRequest, *, index: int = 1) -> dict[str, Any]:
    return {
        "providerId": request.provider_id,
        "projectId": request.project_id,
        "requestSha256": request.scientific_sha256(),
        "pageIndex": index,
        "value": "opaque-scientific-cursor",
        "expiresAt": "2026-01-02T00:00:00.000Z",
    }


def capabilities_document() -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "providerId": "synthetic-provider",
        "adapterVersion": "1.0.0",
        "sourceApiVersion": "fixture-v1",
        "operations": ["citations", "lookup", "oa-resolution", "recommendations", "search"],
        "identifierSchemes": ["doi", "provider-id"],
        "maximumPageSize": 100,
        "configuration": "not-configured",
        "requiredSettings": ["contact", "provider-key"],
    }


class ConnectorContractTests(unittest.TestCase):
    def test_fixture_roundtrips_and_owns_an_immutable_snapshot(self) -> None:
        document = page_document()
        result = ConnectorResultPage.model_validate(document)
        self.assertEqual(document, result.model_dump(mode="json", by_alias=True))
        document["records"][0]["fields"][0]["value"] = "later mutation"
        self.assertNotEqual("later mutation", result.records[0].fields[0].value)
        self.assertIsInstance(result.records, tuple)
        with self.assertRaises(ValidationError):
            result.records[0].provider_id = "substitution"
        self.assertEqual("not-reported", result.records[0].terms.license.state)
        self.assertEqual("unknown", result.records[0].terms.terms.state)

    def test_every_operation_has_a_bounded_scientific_shape(self) -> None:
        identifier = {"scheme": "doi", "value": "10.99999/synthetic-contract"}
        queries = (
            {
                "kind": "search",
                "text": "synthetic topic",
                "field": "any",
                "filters": [],
                "sort": [],
                "fields": ["title"],
            },
            {"kind": "lookup", "identifiers": [identifier]},
            {"kind": "citations", "seed": identifier, "direction": "references"},
            {"kind": "recommendations", "positiveSeeds": [identifier], "negativeSeeds": []},
            {"kind": "oa-resolution", "identifier": identifier},
        )
        for query in queries:
            with self.subTest(operation=query["kind"]):
                request = ConnectorRequest.model_validate(page_document()["request"] | {"query": query})
                self.assertEqual(query, request.query.model_dump(mode="json", by_alias=True))
        for query in (
            {"kind": "lookup", "identifiers": []},
            {"kind": "recommendations", "positiveSeeds": [identifier], "negativeSeeds": [identifier]},
            {"kind": "citations", "seed": identifier, "direction": "unspecified"},
            {"kind": "search", "text": "", "field": "any", "filters": [], "sort": [], "fields": []},
        ):
            with self.subTest(invalid=query), self.assertRaises(ValueError):
                ConnectorRequest.model_validate(page_document()["request"] | {"query": query})

    def test_scientific_identity_excludes_invocation_but_binds_query_and_versions(self) -> None:
        document = page_document()["request"]
        request = ConnectorRequest.model_validate(document)
        repeated = ConnectorRequest.model_validate(document | {"invocationId": "0190a000-0000-7000-8000-000000000012"})
        self.assertEqual(request.scientific_sha256(), repeated.scientific_sha256())
        for delta in (
            {"providerId": "other-provider"},
            {"projectId": "00000000-0000-4000-8000-000000000099"},
            {"adapterVersion": "1.0.1"},
            {"sourceApiVersion": "fixture-v2"},
            {"pageSize": 10},
            {"query": {"kind": "lookup", "identifiers": [{"scheme": "doi", "value": "10.99999/changed"}]}},
        ):
            with self.subTest(delta=delta):
                self.assertNotEqual(
                    request.scientific_sha256(), ConnectorRequest.model_validate(document | delta).scientific_sha256()
                )

    def test_cursor_binding_and_expiry_do_not_grant_resume_authority(self) -> None:
        document = page_document()["request"]
        original = ConnectorRequest.model_validate(document)
        cursor = cursor_document(original)
        resumed = ConnectorRequest.model_validate(document | {"cursor": cursor})
        self.assertEqual(original.scientific_sha256(), resumed.scientific_sha256())
        resumed.assert_resumable("2026-01-01T00:00:00.000Z")
        with self.assertRaisesRegex(ValueError, "cursor-expired"):
            resumed.assert_resumable("2026-01-02T00:00:00.000Z")
        for delta in (
            {"providerId": "other"},
            {"projectId": "00000000-0000-4000-8000-000000000099"},
            {"requestSha256": "sha256:" + "0" * 64},
        ):
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                ConnectorRequest.model_validate(document | {"cursor": cursor | delta})
        with self.assertRaises(ValueError):
            ConnectorRequest.model_validate(document | {"cursor": cursor, "pageSize": 10})

    def test_empty_partial_and_failed_pages_retain_distinct_provenance(self) -> None:
        document = page_document()
        empty = ConnectorResultPage.model_validate(document | {"records": []})
        self.assertEqual("complete", empty.outcome)
        self.assertEqual("lookup", empty.request.query.kind)
        error = {"code": "not-configured", "retryable": False, "retryAfterMs": None}
        failed = document | {
            "outcome": "failed",
            "continuation": "unavailable",
            "records": [],
            "errors": [error],
            "retrievedAt": None,
        }
        denied = ConnectorResultPage.model_validate(failed)
        self.assertEqual("not-configured", denied.errors[0].code)
        self.assertIsNone(denied.retrieved_at)
        partial = document | {
            "outcome": "partial",
            "continuation": "retry-current",
            "errors": [{"code": "partial-response", "retryable": False, "retryAfterMs": None}],
        }
        self.assertEqual(1, len(ConnectorResultPage.model_validate(partial).records))
        for contradictory in (
            failed | {"continuation": "exhausted"},
            failed | {"records": document["records"]},
            document | {"errors": [error]},
            document | {"retrievedAt": None},
            partial | {"errors": []},
        ):
            with self.subTest(contradictory=contradictory["outcome"]), self.assertRaises(ValueError):
                ConnectorResultPage.model_validate(contradictory)

    def test_next_page_must_advance_the_same_scientific_request(self) -> None:
        document = page_document()
        request = ConnectorRequest.model_validate(document["request"])
        cursor = cursor_document(request)
        page = document | {"continuation": "next-page", "nextCursor": cursor}
        next_cursor = ConnectorResultPage.model_validate(page).next_cursor
        assert next_cursor is not None
        self.assertEqual(1, next_cursor.page_index)
        for bad_cursor in (None, cursor | {"pageIndex": 0}, cursor | {"providerId": "other"}):
            with self.subTest(cursor=bad_cursor), self.assertRaises(ValueError):
                ConnectorResultPage.model_validate(page | {"nextCursor": bad_cursor})
        with self.assertRaises(ValueError):
            ConnectorResultPage.model_validate(document | {"nextCursor": cursor})

    def test_authentication_and_contact_shapes_are_not_scientific_parameters(self) -> None:
        document = page_document()["request"]
        for field in ("headers", "url", "apiKey", "contact", "email", "credentialLease"):
            with self.subTest(field=field), self.assertRaises(ValidationError) as caught:
                ConnectorRequest.model_validate(document | {field: "private-sentinel"})
            self.assertNotIn("private-sentinel", str(caught.exception))
        changed = copy.deepcopy(document)
        changed["query"]["headers"] = {"Authorization": "private-sentinel"}
        with self.assertRaises(ValidationError):
            ConnectorRequest.model_validate(changed)
        request = ConnectorRequest.model_validate(document)
        self.assertNotIn("synthetic-contract", repr(request))
        self.assertNotIn("Synthetic contract fixture", repr(ConnectorResultPage.model_validate(page_document())))

    def test_policy_bounds_and_terminal_errors(self) -> None:
        document = page_document()["request"]
        for delta in (
            {"maxInflight": 2},
            {"minimumIntervalMs": 999},
            {"maximumAttempts": 4},
            {"timeoutMs": 30001},
            {"maximumResponseBytes": 10485761},
            {"maximumAttempts": True},
            {"maximumRetryAfterMs": -1},
        ):
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                ConnectorRequest.model_validate(document | {"policy": document["policy"] | delta})
        for code in ("authentication", "permission-denied", "policy-denied", "cancelled", "not-configured"):
            with self.subTest(code=code), self.assertRaises(ValueError):
                ConnectorError(code=code, retryable=True, retry_after_ms=None)
        error = ConnectorError(code="rate-limit", retryable=True, retry_after_ms=2000)
        self.assertEqual("rate-limit", str(ConnectorFailure(error)))
        with self.assertRaises(ValueError):
            ConnectorError.model_validate({"code": "echoed-private-response", "retryable": False, "retryAfterMs": None})

    def test_capabilities_enforce_configuration_version_operation_and_identifiers(self) -> None:
        document = page_document()["request"]
        request = ConnectorRequest.model_validate(document)
        ready = capabilities_document() | {"configuration": "ready"}
        ConnectorCapabilities.model_validate(ready).assert_supported(request)
        for delta in (
            {"configuration": "not-configured"},
            {"providerId": "other"},
            {"adapterVersion": "2.0.0"},
            {"operations": ["search"]},
            {"maximumPageSize": 1},
            {"identifierSchemes": ["provider-id"]},
        ):
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                ConnectorCapabilities.model_validate(ready | delta).assert_supported(request)
        for version in (None, "1.0", "v1", "2026-09"):
            with self.subTest(version=version):
                numeric = ConnectorRequest.model_validate(document | {"sourceApiVersion": version})
                ConnectorCapabilities.model_validate(ready | {"sourceApiVersion": version}).assert_supported(numeric)

    def test_rate_observations_and_terminal_continuations_obey_request(self) -> None:
        document = page_document()
        document["request"]["policy"]["maximumRetryAfterMs"] = 1000
        for delta in ({"observedAt": "2026-01-01T00:00:00.001Z"}, {"retryAfterMs": 1001}):
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                ConnectorResultPage.model_validate(document | {"rate": document["rate"] | delta})
        for code in ("authentication", "permission-denied", "policy-denied", "cancelled", "not-configured"):
            failure = document | {
                "outcome": "failed",
                "records": [],
                "continuation": "retry-current",
                "errors": [{"code": code, "retryable": False, "retryAfterMs": None}],
            }
            with self.subTest(code=code), self.assertRaises(ValueError):
                ConnectorResultPage.model_validate(failure)

    def test_bounds_utc_and_nested_model_revalidation(self) -> None:
        document = page_document()
        for timestamp in ("2026-02-30T00:00:00.000Z", "0000-01-01T00:00:00.000Z", "2026-01-01T00:00:00Z"):
            with self.subTest(timestamp=timestamp), self.assertRaises(ValueError):
                ConnectorResultPage.model_validate(document | {"observedAt": timestamp})
        forged = ConnectorRequest.model_validate(document["request"]).model_copy(update={"page_size": 0})
        with self.assertRaises(ValueError):
            ConnectorResultPage.model_validate(document | {"request": forged})
        huge_field = document["records"][0]["fields"][0] | {"value": "x" * 65536}
        huge_record = document["records"][0] | {"fields": [huge_field] * 170}
        with self.assertRaisesRegex(ValueError, "document-invalid-or-too-large"):
            ConnectorResultPage.model_validate(document | {"records": [huge_record]})
        large_identifiers = [{"scheme": "doi", "value": "x" * 4096}] * 65
        with self.assertRaisesRegex(ValueError, "document-invalid-or-too-large"):
            ConnectorRequest.model_validate(
                document["request"] | {"query": {"kind": "lookup", "identifiers": large_identifiers}}
            )

    def test_retained_response_and_source_json_have_explicit_boundaries(self) -> None:
        document = page_document()
        retained = {
            "bodyState": "retained",
            "objectSha256": "0" * 64,
            "contentSha256": "0" * 64,
            "byteLength": 123,
            "redaction": "applied",
            "reason": "permitted",
        }
        self.assertEqual(
            "retained", ConnectorResultPage.model_validate(document | {"response": retained}).response.body_state
        )
        for delta in ({"contentSha256": "1" * 64}, {"redaction": "unavailable"}, {"byteLength": None}):
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                ConnectorResultPage.model_validate(document | {"response": retained | delta})
        for value in ("NaN", "{broken}", "Infinity"):
            changed = copy.deepcopy(document)
            changed["records"][0]["fields"][0].update(encoding="json", value=value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                ConnectorResultPage.model_validate(changed)

    def test_source_observations_are_not_permissions_and_retention_is_explicit(self) -> None:
        document = page_document()
        for changes in (
            {"state": "allowed", "value": None},
            {"state": "unknown", "value": "permission"},
            {"state": "reported", "value": None},
        ):
            changed = copy.deepcopy(document)
            changed["records"][0]["terms"]["license"] = changes
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                ConnectorResultPage.model_validate(changed)
        for changes in ({"bodyState": "retained"}, {"objectSha256": "sha256:" + "0" * 64}, {"path": "local-data"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                ConnectorResultPage.model_validate(document | {"response": document["response"] | changes})
        changed = copy.deepcopy(document)
        changed["records"][0]["providerId"] = "other-provider"
        with self.assertRaises(ValueError):
            ConnectorResultPage.model_validate(changed)

    def test_cache_observations_bind_request_and_declared_freshness(self) -> None:
        document = page_document()
        document["request"]["policy"].update(cacheMode="allow-fresh", maximumFreshAgeMs=1000)
        request = ConnectorRequest.model_validate(document["request"])
        cache = {"state": "hit", "ageMs": 500, "requestSha256": request.page_sha256()}
        self.assertEqual("hit", ConnectorResultPage.model_validate(document | {"cache": cache}).cache.state)
        for delta in ({"ageMs": 1001}, {"ageMs": None}, {"requestSha256": "sha256:" + "0" * 64}):
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                ConnectorResultPage.model_validate(document | {"cache": cache | delta})
        resumed = copy.deepcopy(document)
        resumed["request"]["cursor"] = cursor_document(request)
        with self.assertRaisesRegex(ValueError, "cache-binding-invalid"):
            ConnectorResultPage.model_validate(resumed | {"cache": cache})

    def test_published_schemas_are_generated_and_reject_unknown_wire_fields(self) -> None:
        from core_api_contract import generated_artifacts

        generated = generated_artifacts(REPO)
        for filename, model, fixture in (
            ("connector-request.schema.json", ConnectorRequest, page_document()["request"]),
            ("connector-page.schema.json", ConnectorResultPage, page_document()),
            ("connector-capabilities.schema.json", ConnectorCapabilities, capabilities_document()),
        ):
            with self.subTest(filename=filename):
                path = REPO / "packages/contracts/connectors" / filename
                self.assertEqual(generated[path], path.read_bytes())
                schema = json.loads(generated[path])
                Draft202012Validator.check_schema(schema)
                validator = Draft202012Validator(schema)
                self.assertTrue(validator.is_valid(fixture))
                self.assertFalse(validator.is_valid(fixture | {"headers": {}}))
                model.model_validate(fixture)


class ConnectorPortTests(unittest.IsolatedAsyncioTestCase):
    async def test_adapter_is_replaceable_and_needs_no_network_or_secret_handle(self) -> None:
        class Cancellation:
            cancelled = False

        class FixtureAdapter:
            def describe(self) -> ConnectorCapabilities:
                return ConnectorCapabilities.model_validate(capabilities_document() | {"configuration": "ready"})

            async def fetch(self, request: ConnectorRequest, *, cancellation: Any) -> ConnectorResultPage:
                if cancellation.cancelled:
                    raise ConnectorFailure(ConnectorError(code="cancelled", retryable=False, retry_after_ms=None))
                return ConnectorResultPage.model_validate(
                    page_document() | {"request": request.model_dump(mode="json", by_alias=True)}
                )

        adapter: ConnectorAdapter = FixtureAdapter()
        self.assertIsInstance(adapter, ConnectorAdapter)
        request = ConnectorRequest.model_validate(page_document()["request"])
        result = await adapter.fetch(request, cancellation=Cancellation())
        self.assertEqual(request.scientific_sha256(), result.request.scientific_sha256())
        cancelled = Cancellation()
        cancelled.cancelled = True
        with self.assertRaisesRegex(ConnectorFailure, "cancelled"):
            await adapter.fetch(request, cancellation=cancelled)


if __name__ == "__main__":
    unittest.main()
