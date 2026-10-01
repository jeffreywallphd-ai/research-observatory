"""Signed connector package admission and project-scoped invocation planning.

This module does not load or run plugin code. The isolated worker and the broker
must recheck the resulting plan at dispatch time (CAP-04.S05.T02).
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, Self

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey
from pydantic import ConfigDict, Field, field_validator, model_validator

from ..models import ContractModel
from .contracts import InvocationId, ProjectId

_MAX_MANIFEST_BYTES = 64 * 1024
_MAX_PACKAGE_BYTES = 64 * 1024 * 1024
_MAX_FILE_BYTES = 16 * 1024 * 1024
_SDK_MAJOR = 1
_VERIFIED_SEAL = object()
_IDENTIFIER = r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$"
_KEY_ID = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
_DIGEST = r"^sha256:[0-9a-f]{64}$"
_SEMVER = r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$"
_SCOPE = r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$"
_HOST = re.compile(r"^(?=.{1,253}$)[a-z0-9]+(?:-[a-z0-9]+)*(?:\.[a-z0-9]+(?:-[a-z0-9]+)*)+$")
_PATH_PART = re.compile(r"^(?:[A-Za-z0-9._~-]|\{[a-z][a-z0-9_]*\})+$")
_WINDOWS_DEVICES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}

type PluginId = Annotated[str, Field(strict=True, pattern=_IDENTIFIER, max_length=128)]
type Version = Annotated[str, Field(strict=True, pattern=_SEMVER, max_length=64)]
type KeyId = Annotated[str, Field(strict=True, pattern=_KEY_ID)]
type Sha256 = Annotated[str, Field(strict=True, pattern=_DIGEST)]
type Scope = Annotated[str, Field(strict=True, pattern=_SCOPE, max_length=128)]
type Operation = Literal["lookup", "search", "references", "citations", "open-access-locations", "repository-metadata"]
type Permission = Literal["provider-network", "credential-broker"]
type DataClass = Literal["public-metadata", "licensed-metadata", "private-query", "full-text"]
type RequiredFeature = Literal["source-assertions-v1", "brokered-requests-v1"]


class _PluginModel(ContractModel):
    model_config = ConfigDict(revalidate_instances="always", hide_input_in_errors=True)


def _valid_package_path(path: str) -> bool:
    if not path or len(path) > 240 or path.startswith("/") or "\\" in path or ":" in path or "\x00" in path:
        return False
    for part in path.split("/"):
        if (
            not part
            or part in {".", ".."}
            or part.endswith((".", " "))
            or any(ord(char) < 32 or ord(char) == 127 for char in part)
            or part.split(".", 1)[0].casefold() in _WINDOWS_DEVICES
            or re.fullmatch(r"[A-Za-z0-9._-]+", part) is None
        ):
            return False
    return True


class PluginFile(_PluginModel):
    path: Annotated[str, Field(strict=True, min_length=1, max_length=240)]
    sha256: Sha256

    @field_validator("path")
    @classmethod
    def safe_relative_path(cls, value: str) -> str:
        if not _valid_package_path(value):
            raise ValueError("plugin-file-path-unsafe")
        return value


class PluginDestination(_PluginModel):
    scheme: Literal["https"]
    host: Annotated[str, Field(strict=True, min_length=1, max_length=253)]
    port: Annotated[int, Field(strict=True, ge=1, le=65535)]
    path_template: Annotated[str, Field(strict=True, min_length=1, max_length=256)]

    @field_validator("host")
    @classmethod
    def public_dns_name(cls, value: str) -> str:
        if _HOST.fullmatch(value) is None or value.endswith((".localhost", ".local", ".internal")):
            raise ValueError("plugin-destination-host-invalid")
        try:
            ipaddress.ip_address(value)
        except ValueError:
            return value
        raise ValueError("plugin-destination-ip-not-allowed")

    @field_validator("path_template")
    @classmethod
    def bounded_path_template(cls, value: str) -> str:
        if not value.startswith("/") or value.startswith("//"):
            raise ValueError("plugin-destination-path-invalid")
        parts = value[1:].split("/")
        if any(part in {"", ".", ".."} or _PATH_PART.fullmatch(part) is None for part in parts if value != "/"):
            raise ValueError("plugin-destination-path-invalid")
        return value


class PluginSourceIdentity(_PluginModel):
    source_id: PluginId
    display_name: Annotated[str, Field(strict=True, min_length=1, max_length=128)]

    @field_validator("display_name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        if not value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("plugin-source-name-invalid")
        return value


class PluginAuthentication(_PluginModel):
    mode: Literal["none", "broker-scoped"]


class PluginTerms(_PluginModel):
    """A provider declaration; it never authorizes any rights action."""

    status: Literal["not-reported", "declared"]
    reference: Annotated[str, Field(strict=True, min_length=1, max_length=512)] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def coherent_declaration(self) -> Self:
        if (self.status == "declared") != (self.reference is not None):
            raise ValueError("plugin-terms-declaration-invalid")
        return self


class PluginRateLimits(_PluginModel):
    max_requests_per_second: Annotated[int, Field(strict=True, ge=1, le=10)]
    max_concurrent: Annotated[int, Field(strict=True, ge=1, le=1)]


class PluginResourceProfile(_PluginModel):
    committed_memory_mi_b: Annotated[int, Field(strict=True, ge=16, le=256)]
    max_jobs_per_project: Annotated[int, Field(strict=True, ge=1, le=1)]
    wall_time_seconds: Annotated[int, Field(strict=True, ge=1, le=60)]


class PluginManifest(_PluginModel):
    schema_version: Literal["1.0"]
    plugin_id: PluginId
    plugin_version: Version
    sdk_version: Version
    required_features: Annotated[tuple[RequiredFeature, ...], Field(max_length=2)]
    publisher_key_id: KeyId
    source_identity: PluginSourceIdentity
    authentication: PluginAuthentication
    terms: PluginTerms
    rate_limits: PluginRateLimits
    entry_point: Annotated[str, Field(strict=True, min_length=1, max_length=240)]
    files: Annotated[tuple[PluginFile, ...], Field(min_length=1, max_length=128)]
    operations: Annotated[tuple[Operation, ...], Field(min_length=1, max_length=6)]
    destinations: Annotated[tuple[PluginDestination, ...], Field(max_length=16)]
    credential_scopes: Annotated[tuple[Scope, ...], Field(max_length=16)]
    data_classes: Annotated[tuple[DataClass, ...], Field(min_length=1, max_length=4)]
    rights_behavior: Literal["source-assertions-only"]
    resource_profile: PluginResourceProfile
    permissions: Annotated[tuple[Permission, ...], Field(max_length=2)]

    @model_validator(mode="after")
    def bounded_capabilities(self) -> Self:
        if int(self.sdk_version.split(".", 1)[0]) != _SDK_MAJOR:
            raise ValueError("plugin-sdk-major-incompatible")
        # Plugin assertions have their own namespace; a signed third-party
        # manifest must not impersonate a built-in source such as openalex.
        if self.source_identity.source_id != f"plugin.{self.plugin_id}":
            raise ValueError("plugin-source-identity-unqualified")
        paths = [item.path for item in self.files]
        if len({path.casefold() for path in paths}) != len(paths):
            raise ValueError("plugin-file-path-duplicate")
        if (
            self.entry_point not in paths
            or not self.entry_point.startswith("plugin/")
            or not self.entry_point.endswith(".py")
        ):
            raise ValueError("plugin-entry-point-invalid")
        for values in (
            self.required_features,
            self.operations,
            self.destinations,
            self.credential_scopes,
            self.data_classes,
            self.permissions,
        ):
            if len(set(values)) != len(values):
                raise ValueError("plugin-capability-duplicate")
        if (self.authentication.mode == "none") != (not self.credential_scopes):
            raise ValueError("plugin-authentication-scopes-invalid")
        if self.authentication.mode == "broker-scoped" and "credential-broker" not in self.permissions:
            raise ValueError("plugin-credential-permission-missing")
        if self.authentication.mode == "none" and "credential-broker" in self.permissions:
            raise ValueError("plugin-credential-permission-unused")
        if self.destinations and "provider-network" not in self.permissions:
            raise ValueError("plugin-network-permission-missing")
        if "provider-network" in self.permissions and not self.destinations:
            raise ValueError("plugin-network-destination-missing")
        return self


@dataclass(frozen=True, slots=True)
class VerifiedPluginPackage:
    manifest: PluginManifest
    manifest_sha256: str
    package_sha256: str
    signature_sha256: str
    _seal: object = field(repr=False, compare=False)


class PluginProjectGrant(_PluginModel):
    project_id: ProjectId
    plugin_id: PluginId
    plugin_version: Version
    package_sha256: Sha256
    manifest_sha256: Sha256
    publisher_key_id: KeyId
    permissions: Annotated[tuple[Permission, ...], Field(max_length=2)]
    destinations: Annotated[tuple[PluginDestination, ...], Field(max_length=16)]
    revision: Annotated[int, Field(strict=True, ge=1, le=2**53 - 1)]

    @model_validator(mode="after")
    def unique_grant(self) -> Self:
        if len(set(self.permissions)) != len(self.permissions) or len(set(self.destinations)) != len(self.destinations):
            raise ValueError("plugin-grant-duplicate")
        return self


class PluginInvocationRequest(_PluginModel):
    project_id: ProjectId
    invocation_id: InvocationId
    scientific_request_sha256: Sha256
    operation: Operation
    destination: PluginDestination


class PluginInvocationPlan(_PluginModel):
    plugin_id: PluginId
    plugin_version: Version
    sdk_version: Version
    required_features: tuple[RequiredFeature, ...]
    source_id: PluginId
    package_sha256: Sha256
    manifest_sha256: Sha256
    publisher_key_id: KeyId
    signature_sha256: Sha256
    project_id: ProjectId
    grant_revision: Annotated[int, Field(strict=True, ge=1)]
    permissions: tuple[Permission, ...]
    invocation_id: InvocationId
    scientific_request_sha256: Sha256
    request_sha256: Sha256
    operation: Operation
    destination: PluginDestination


class PluginAuthorizationProvenance(PluginInvocationPlan):
    """An authorized decision only, not authority when deserialized as data."""

    schema_version: Literal["1.0"]
    phase: Literal["authorized"]


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("plugin-manifest-duplicate-key")
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise ValueError("plugin-manifest-nonfinite-number")


def verify_plugin_package(
    manifest_bytes: bytes,
    signature: bytes,
    package_files: Mapping[str, bytes],
    trusted_keys: Mapping[str, bytes],
) -> VerifiedPluginPackage:
    """Admit only exact signed bytes and the complete declared file set.

    The package digest is SHA-256 over a domain tag followed by sorted file
    entries, each encoded as a 4-byte path length, UTF-8 path, 8-byte content
    length and exact content bytes. It does not depend on archive metadata.
    """

    if not isinstance(manifest_bytes, bytes) or not 0 < len(manifest_bytes) <= _MAX_MANIFEST_BYTES:
        raise ValueError("plugin-manifest-size-invalid")
    if not isinstance(signature, bytes) or len(signature) != 64:
        raise ValueError("plugin-signature-invalid")
    try:
        document = json.loads(
            manifest_bytes.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except UnicodeError, ValueError, RecursionError:
        raise ValueError("plugin-manifest-json-invalid") from None
    if not isinstance(document, dict) or not isinstance(document.get("publisherKeyId"), str):
        raise ValueError("plugin-manifest-publisher-missing")
    key = trusted_keys.get(document["publisherKeyId"])
    if not isinstance(key, bytes) or len(key) != 32:
        raise ValueError("plugin-publisher-untrusted")
    try:
        VerifyKey(key).verify(manifest_bytes, signature)
    except BadSignatureError, ValueError, TypeError:
        raise ValueError("plugin-signature-invalid") from None
    manifest = PluginManifest.model_validate(document)
    if not isinstance(package_files, Mapping) or len(package_files) != len(manifest.files):
        raise ValueError("plugin-package-file-set-invalid")
    declared = {item.path: item for item in manifest.files}
    if set(package_files) != set(declared):
        raise ValueError("plugin-package-file-set-invalid")
    package_hash = hashlib.sha256(b"research-observatory-connector-package-v1\x00")
    total_bytes = 0
    for path in sorted(declared):
        raw = package_files[path]
        if not isinstance(raw, bytes) or len(raw) > _MAX_FILE_BYTES:
            raise ValueError("plugin-package-file-invalid")
        total_bytes += len(raw)
        if total_bytes > _MAX_PACKAGE_BYTES or _sha256(raw) != declared[path].sha256:
            raise ValueError("plugin-package-file-hash-invalid")
        encoded_path = path.encode("utf-8")
        package_hash.update(len(encoded_path).to_bytes(4, "big"))
        package_hash.update(encoded_path)
        package_hash.update(len(raw).to_bytes(8, "big"))
        package_hash.update(raw)
    return VerifiedPluginPackage(
        manifest=manifest,
        manifest_sha256=_sha256(manifest_bytes),
        package_sha256="sha256:" + package_hash.hexdigest(),
        signature_sha256=_sha256(signature),
        _seal=_VERIFIED_SEAL,
    )


def authorize_plugin_invocation(
    package: VerifiedPluginPackage,
    grant: PluginProjectGrant,
    request: PluginInvocationRequest,
) -> PluginInvocationPlan:
    """Plan only from a Core-owned, active, researcher-approved project grant.

    Caller authentication and grant persistence are owned by the Core enable
    workflow; this function does not accept plugin-supplied consent or dispatch
    a worker. A new package, manifest or permission set needs a new active grant.
    """

    if not isinstance(package, VerifiedPluginPackage) or package._seal is not _VERIFIED_SEAL:
        raise ValueError("plugin-package-unverified")
    grant = PluginProjectGrant.model_validate(grant.model_dump(mode="json", by_alias=True))
    request = PluginInvocationRequest.model_validate(request.model_dump(mode="json", by_alias=True))
    manifest = package.manifest
    if (
        grant.project_id != request.project_id
        or grant.plugin_id != manifest.plugin_id
        or grant.plugin_version != manifest.plugin_version
        or grant.package_sha256 != package.package_sha256
        or grant.manifest_sha256 != package.manifest_sha256
        or grant.publisher_key_id != manifest.publisher_key_id
        or set(grant.permissions) != set(manifest.permissions)
        or set(grant.destinations) != set(manifest.destinations)
    ):
        raise ValueError("plugin-project-grant-mismatch")
    if request.operation not in manifest.operations or request.destination not in manifest.destinations:
        raise ValueError("plugin-invocation-capability-denied")
    # This hash identifies the routing request, including the Core-owned digest
    # of protected scientific input. It is not a wire URL/body or replay bytes.
    request_bytes = json.dumps(
        request.model_dump(mode="json", by_alias=True),
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return PluginInvocationPlan(
        plugin_id=manifest.plugin_id,
        plugin_version=manifest.plugin_version,
        sdk_version=manifest.sdk_version,
        required_features=manifest.required_features,
        source_id=manifest.source_identity.source_id,
        package_sha256=package.package_sha256,
        manifest_sha256=package.manifest_sha256,
        publisher_key_id=manifest.publisher_key_id,
        signature_sha256=package.signature_sha256,
        project_id=request.project_id,
        grant_revision=grant.revision,
        permissions=tuple(sorted(grant.permissions)),
        invocation_id=request.invocation_id,
        scientific_request_sha256=request.scientific_request_sha256,
        request_sha256=_sha256(request_bytes),
        operation=request.operation,
        destination=request.destination,
    )


def authorization_provenance(
    package: VerifiedPluginPackage,
    grant: PluginProjectGrant,
    request: PluginInvocationRequest,
) -> PluginAuthorizationProvenance:
    """Recheck authorization before describing its authorized-phase decision.

    A caller cannot mint this envelope from plan-shaped JSON. Core persists a
    decision, dispatch/result and response lineage separately; constructing
    this value does not claim that any of them occurred.
    """

    plan = authorize_plugin_invocation(package, grant, request)
    return PluginAuthorizationProvenance.model_validate(
        {**plan.model_dump(mode="json", by_alias=True), "schemaVersion": "1.0", "phase": "authorized"}
    )
