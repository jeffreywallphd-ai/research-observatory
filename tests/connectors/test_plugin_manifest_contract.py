"""Synthetic signed-plugin admission tests; LPAC execution belongs to S05.T02."""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator
from nacl.signing import SigningKey

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services/core-api/src"))
sys.path.insert(0, str(REPO / "tools"))

from research_observatory_core.connectors.plugin_manifest import (  # noqa: E402
    PluginAuthorizationProvenance,
    PluginInvocationRequest,
    PluginManifest,
    PluginProjectGrant,
    authorization_provenance,
    authorize_plugin_invocation,
    verify_plugin_package,
)

PROJECT_ID = "0190a000-0000-7000-8000-000000000040"
OTHER_PROJECT_ID = "0190a000-0000-7000-8000-000000000041"
INVOCATION_ID = "0190a000-0000-7000-8000-000000000042"
SCIENTIFIC_DIGEST = "sha256:" + "a" * 64
PUBLISHER_ID = "fixture-repository-publisher"
PATH = "plugin/connector.py"
DESTINATION = {
    "scheme": "https",
    "host": "repository.example.invalid",
    "port": 443,
    "pathTemplate": "/v1/records",
}
PACKAGE_FILE = b"# synthetic package bytes; never executed\n"


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _manifest_document(*, package_file: bytes = PACKAGE_FILE) -> dict:
    return {
        "schemaVersion": "1.0",
        "pluginId": "fixture.repository",
        "pluginVersion": "1.0.0",
        "sdkVersion": "1.0.0",
        "requiredFeatures": ["source-assertions-v1", "brokered-requests-v1"],
        "publisherKeyId": PUBLISHER_ID,
        "sourceIdentity": {"sourceId": "plugin.fixture.repository", "displayName": "Synthetic repository"},
        "authentication": {"mode": "none"},
        "terms": {"status": "not-reported"},
        "rateLimits": {"maxRequestsPerSecond": 1, "maxConcurrent": 1},
        "entryPoint": PATH,
        "files": [{"path": PATH, "sha256": _digest(package_file)}],
        "operations": ["lookup", "repository-metadata"],
        "destinations": [DESTINATION],
        "credentialScopes": [],
        "dataClasses": ["public-metadata"],
        "rightsBehavior": "source-assertions-only",
        "resourceProfile": {"committedMemoryMiB": 256, "maxJobsPerProject": 1, "wallTimeSeconds": 60},
        "permissions": ["provider-network"],
    }


def _manifest_bytes(document: dict) -> bytes:
    # Verification must use these exact bytes, not reserialized JSON.
    return json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _grant(verified, **changes) -> PluginProjectGrant:
    data = {
        "projectId": PROJECT_ID,
        "pluginId": verified.manifest.plugin_id,
        "pluginVersion": verified.manifest.plugin_version,
        "packageSha256": verified.package_sha256,
        "manifestSha256": verified.manifest_sha256,
        "publisherKeyId": verified.manifest.publisher_key_id,
        "permissions": ["provider-network"],
        "destinations": [DESTINATION],
        "revision": 1,
    }
    data.update(changes)
    return PluginProjectGrant.model_validate(data)


def _request(**changes) -> PluginInvocationRequest:
    data = {
        "projectId": PROJECT_ID,
        "invocationId": INVOCATION_ID,
        "scientificRequestSha256": SCIENTIFIC_DIGEST,
        "operation": "lookup",
        "destination": DESTINATION,
    }
    data.update(changes)
    return PluginInvocationRequest.model_validate(data)


class PluginManifestContractTests(unittest.TestCase):
    def setUp(self) -> None:
        # Disposable synthetic key. No application trust store or live publisher is used.
        self.key = SigningKey(b"\x01" * 32)
        self.trusted_keys = {PUBLISHER_ID: bytes(self.key.verify_key)}

    def verify(self, document=None, *, package_file=PACKAGE_FILE, key=None, trust=None):
        raw = _manifest_bytes(document if document is not None else _manifest_document(package_file=package_file))
        signer = self.key if key is None else key
        return verify_plugin_package(
            raw,
            signer.sign(raw).signature,
            {PATH: package_file},
            self.trusted_keys if trust is None else trust,
        )

    def test_valid_exact_signed_package_has_distinct_manifest_and_package_identity(self):
        verified = self.verify()
        self.assertEqual("fixture.repository", verified.manifest.plugin_id)
        self.assertEqual("1.0.0", verified.manifest.plugin_version)
        self.assertEqual(_digest(_manifest_bytes(_manifest_document())), verified.manifest_sha256)
        self.assertTrue(verified.package_sha256.startswith("sha256:"))
        self.assertNotEqual(verified.manifest_sha256, verified.package_sha256)

    def test_signature_trust_exact_bytes_and_file_hashes_fail_closed(self):
        document = _manifest_document()
        raw = _manifest_bytes(document)
        signature = self.key.sign(raw).signature
        self.assertIsNotNone(verify_plugin_package(raw, signature, {PATH: PACKAGE_FILE}, self.trusted_keys))
        with self.assertRaises(ValueError):
            verify_plugin_package(raw, b"", {PATH: PACKAGE_FILE}, self.trusted_keys)
        # Trust must be a separate local decision, not a key claimed by the package.
        for trusted in ({}, {PUBLISHER_ID: bytes(SigningKey(b"\x02" * 32).verify_key)}):
            with self.subTest(trusted=bool(trusted)), self.assertRaises(ValueError):
                verify_plugin_package(raw, signature, {PATH: PACKAGE_FILE}, trusted)
        for changed_raw, changed_files in (
            (raw + b" ", {PATH: PACKAGE_FILE}),
            (raw, {PATH: PACKAGE_FILE + b"tampered"}),
            (raw, {"plugin/other.py": PACKAGE_FILE}),
        ):
            with self.subTest(raw=changed_raw != raw, files=tuple(changed_files)), self.assertRaises(ValueError):
                verify_plugin_package(changed_raw, signature, changed_files, self.trusted_keys)
        substituted_entry = _manifest_document()
        substituted_entry["entryPoint"] = "plugin/other.py"
        with self.assertRaises(ValueError):
            self.verify(substituted_entry)
        with self.assertRaises(ValueError):
            verify_plugin_package(
                raw,
                signature,
                {PATH: PACKAGE_FILE, "plugin/undeclared.py": b"unexpected"},
                self.trusted_keys,
            )

    def test_signed_duplicate_keys_unsafe_paths_and_destinations_still_deny(self):
        raw = _manifest_bytes(_manifest_document())
        duplicate_id = raw.replace(
            b'"pluginId":"fixture.repository"',
            b'"pluginId":"fixture.repository","pluginId":"fixture.other"',
            1,
        )
        self.assertNotEqual(raw, duplicate_id)
        with self.assertRaises(ValueError):
            verify_plugin_package(
                duplicate_id,
                self.key.sign(duplicate_id).signature,
                {PATH: PACKAGE_FILE},
                self.trusted_keys,
            )
        unsafe = _manifest_document()
        unsafe["entryPoint"] = "../connector.py"
        unsafe["files"][0]["path"] = "../connector.py"
        unsafe_raw = _manifest_bytes(unsafe)
        with self.assertRaises(ValueError):
            verify_plugin_package(
                unsafe_raw,
                self.key.sign(unsafe_raw).signature,
                {"../connector.py": PACKAGE_FILE},
                self.trusted_keys,
            )
        alias = _manifest_document()
        alias_path = "plugin/CONNECTOR.py"
        alias["files"].append({"path": alias_path, "sha256": _digest(PACKAGE_FILE)})
        alias_raw = _manifest_bytes(alias)
        with self.assertRaises(ValueError):
            verify_plugin_package(
                alias_raw,
                self.key.sign(alias_raw).signature,
                {PATH: PACKAGE_FILE, alias_path: PACKAGE_FILE},
                self.trusted_keys,
            )
        for host in ("*.example.invalid", "127.0.0.1", "localhost"):
            destination = _manifest_document()
            destination["destinations"] = [DESTINATION | {"host": host}]
            with self.subTest(host=host), self.assertRaises(ValueError):
                self.verify(destination)

    def test_signed_source_authentication_terms_and_rate_declarations_are_required(self):
        for field in ("sourceIdentity", "authentication", "terms", "rateLimits"):
            incomplete = _manifest_document()
            del incomplete[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.verify(incomplete)
        first_party_impersonation = _manifest_document()
        first_party_impersonation["sourceIdentity"]["sourceId"] = "openalex"
        with self.assertRaises(ValueError):
            self.verify(first_party_impersonation)
        no_auth_with_scopes = _manifest_document()
        no_auth_with_scopes["credentialScopes"] = ["repository-token"]
        with self.assertRaises(ValueError):
            self.verify(no_auth_with_scopes)
        no_rate_limit = _manifest_document()
        no_rate_limit["rateLimits"]["maxRequestsPerSecond"] = 0
        with self.assertRaises(ValueError):
            self.verify(no_rate_limit)

    def test_namespaced_source_identity_plugin_id_length_boundary(self):
        largest = "a" * 121
        valid = _manifest_document()
        valid["pluginId"] = largest
        valid["sourceIdentity"]["sourceId"] = "plugin." + largest
        self.assertEqual(128, len(valid["sourceIdentity"]["sourceId"]))
        verified = self.verify(valid)
        plan = authorize_plugin_invocation(verified, _grant(verified), _request())
        self.assertEqual(largest, plan.plugin_id)
        self.assertEqual("plugin." + largest, plan.source_id)
        overlong = _manifest_document()
        overlong["pluginId"] = "a" * 122
        overlong["sourceIdentity"]["sourceId"] = "plugin." + overlong["pluginId"]
        with self.assertRaises(ValueError):
            self.verify(overlong)

    def test_authorized_plan_attributes_exact_plugin_grant_and_request_without_secrets(self):
        verified = self.verify()
        grant = _grant(verified)
        request = _request()
        plan = authorize_plugin_invocation(verified, grant, request)
        evidence = plan.model_dump(mode="json", by_alias=True)
        self.assertEqual("fixture.repository", evidence["pluginId"])
        self.assertEqual("plugin.fixture.repository", evidence["sourceId"])
        self.assertEqual("1.0.0", evidence["pluginVersion"])
        self.assertEqual(verified.package_sha256, evidence["packageSha256"])
        self.assertEqual(verified.manifest_sha256, evidence["manifestSha256"])
        self.assertEqual(PUBLISHER_ID, evidence["publisherKeyId"])
        self.assertEqual(PROJECT_ID, evidence["projectId"])
        self.assertEqual(1, evidence["grantRevision"])
        self.assertEqual(["provider-network"], evidence["permissions"])
        self.assertEqual("lookup", evidence["operation"])
        self.assertEqual(INVOCATION_ID, evidence["invocationId"])
        self.assertEqual(SCIENTIFIC_DIGEST, evidence["scientificRequestSha256"])
        decision = authorization_provenance(verified, grant, request).model_dump(mode="json", by_alias=True)
        self.assertEqual("authorized", decision["phase"])
        self.assertEqual("1.0", decision["schemaVersion"])
        for key in (
            "pluginId",
            "pluginVersion",
            "sourceId",
            "packageSha256",
            "manifestSha256",
            "publisherKeyId",
            "projectId",
            "grantRevision",
            "permissions",
            "invocationId",
            "scientificRequestSha256",
            "requestSha256",
            "operation",
            "destination",
        ):
            self.assertEqual(evidence[key], decision[key], key)
        self.assertNotIn("secret", json.dumps(evidence).lower())
        self.assertNotIn("C:\\", json.dumps(evidence))

    def test_authorized_provenance_requires_verified_package_and_matching_grant(self):
        verified = self.verify()
        grant = _grant(verified)
        request = _request()
        forged_plan = authorize_plugin_invocation(verified, grant, request).model_copy(
            update={"package_sha256": "sha256:" + "0" * 64}
        )
        with self.assertRaises(ValueError):
            authorization_provenance(cast(Any, forged_plan), grant, request)
        with self.assertRaises(ValueError):
            authorization_provenance(
                verified,
                _grant(verified, packageSha256="sha256:" + "0" * 64),
                request,
            )

    def test_unsupported_plugin_operation_and_sdk_major_deny_before_plan(self):
        verified = self.verify()
        grant = _grant(verified)
        for operation in ("search", "recommendations", "oa-resolution", "download", "arbitrary-http"):
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                authorize_plugin_invocation(verified, grant, _request(operation=operation))
        incompatible = _manifest_document()
        incompatible["sdkVersion"] = "2.0.0"
        with self.assertRaises(ValueError):
            updated = self.verify(incompatible)
            authorize_plugin_invocation(updated, _grant(updated), _request())

    def test_scientific_request_digest_changes_exact_invocation_identity(self):
        verified = self.verify()
        grant = _grant(verified)
        first = authorize_plugin_invocation(verified, grant, _request())
        different_science = "sha256:" + "b" * 64
        second = authorize_plugin_invocation(
            verified,
            grant,
            _request(scientificRequestSha256=different_science),
        )
        self.assertEqual(first.invocation_id, second.invocation_id)
        self.assertEqual(first.operation, second.operation)
        self.assertEqual(first.destination, second.destination)
        self.assertNotEqual(first.request_sha256, second.request_sha256)
        self.assertEqual(SCIENTIFIC_DIGEST, first.scientific_request_sha256)
        self.assertEqual(different_science, second.scientific_request_sha256)
        different_route = authorize_plugin_invocation(
            verified,
            grant,
            _request(operation="repository-metadata"),
        )
        self.assertEqual(SCIENTIFIC_DIGEST, different_route.scientific_request_sha256)
        self.assertNotEqual(first.request_sha256, different_route.request_sha256)

    def test_sdk_same_major_minor_negotiates_only_known_required_features(self):
        same_major = _manifest_document()
        same_major["sdkVersion"] = "1.1.0"
        verified = self.verify(same_major)
        self.assertEqual("1.1.0", verified.manifest.sdk_version)
        self.assertEqual("lookup", authorize_plugin_invocation(verified, _grant(verified), _request()).operation)
        unknown_feature = _manifest_document()
        unknown_feature["requiredFeatures"] = ["source-assertions-v1", "future-unreviewed-feature-v1"]
        with self.assertRaises(ValueError):
            self.verify(unknown_feature)

    def test_grant_and_destination_substitutions_deny_before_plan(self):
        verified = self.verify()
        grant = _grant(verified)
        changes: tuple[dict[str, object], ...] = (
            {"projectId": OTHER_PROJECT_ID},
            {"pluginId": "fixture.other"},
            {"manifestSha256": "sha256:" + "0" * 64},
            {"packageSha256": "sha256:" + "0" * 64},
            {"publisherKeyId": "other-publisher"},
            {"permissions": []},
            {"destinations": []},
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                authorize_plugin_invocation(verified, _grant(verified, **change), _request())
        for destination in (
            DESTINATION | {"scheme": "http"},
            DESTINATION | {"host": "private.example.invalid"},
            DESTINATION | {"port": 8443},
            DESTINATION | {"pathTemplate": "/other"},
        ):
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                authorize_plugin_invocation(verified, grant, _request(destination=destination))

    def test_same_version_changed_package_requires_new_project_enable(self):
        original = self.verify()
        original_grant = _grant(original)
        changed_bytes = PACKAGE_FILE + b"# revised\n"
        updated = self.verify(_manifest_document(package_file=changed_bytes), package_file=changed_bytes)
        self.assertEqual(original.manifest.plugin_version, updated.manifest.plugin_version)
        self.assertNotEqual(original.package_sha256, updated.package_sha256)
        with self.assertRaises(ValueError):
            authorize_plugin_invocation(updated, original_grant, _request())
        renewed = _grant(updated, revision=2)
        plan = authorize_plugin_invocation(updated, renewed, _request())
        self.assertEqual(updated.package_sha256, plan.package_sha256)
        self.assertEqual(2, plan.grant_revision)

    def test_existing_first_party_page_fixture_remains_readable(self):
        from research_observatory_core.connectors.contracts import ConnectorResultPage

        fixture = json.loads((REPO / "tests/fixtures/scholarly-metadata/connector-page.v1.json").read_text("utf-8"))
        page = ConnectorResultPage.model_validate(fixture)
        self.assertEqual(fixture, page.model_dump(mode="json", by_alias=True))

    def test_published_manifest_and_authorization_plan_schemas_round_trip_without_drift(self):
        from core_api_contract import generated_artifacts

        verified = self.verify()
        grant = _grant(verified)
        request = _request()
        plan = authorize_plugin_invocation(verified, grant, request)
        authorization = authorization_provenance(verified, grant, request)
        generated = generated_artifacts(REPO)
        for filename, model, document in (
            ("connector-plugin-manifest.schema.json", PluginManifest, _manifest_document()),
            ("connector-plugin-grant.schema.json", PluginProjectGrant, grant.model_dump(mode="json", by_alias=True)),
            (
                "connector-plugin-invocation-request.schema.json",
                PluginInvocationRequest,
                request.model_dump(mode="json", by_alias=True),
            ),
            (
                "connector-plugin-invocation-plan.schema.json",
                type(plan),
                plan.model_dump(mode="json", by_alias=True),
            ),
            (
                "connector-plugin-authorization-provenance.schema.json",
                PluginAuthorizationProvenance,
                authorization.model_dump(mode="json", by_alias=True),
            ),
        ):
            with self.subTest(filename=filename):
                path = REPO / "packages/contracts/connectors" / filename
                self.assertEqual(generated[path], path.read_bytes())
                schema = json.loads(generated[path])
                Draft202012Validator.check_schema(schema)
                validator = Draft202012Validator(schema)
                self.assertTrue(validator.is_valid(document))
                self.assertFalse(validator.is_valid(document | {"ambientProfilePath": "C:/fixture"}))
                self.assertEqual(
                    document,
                    model.model_validate(document).model_dump(mode="json", by_alias=True, exclude_none=True),
                )


if __name__ == "__main__":
    unittest.main()
