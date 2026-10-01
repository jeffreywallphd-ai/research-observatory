"""Profile-local publisher keys and Core-only project plugin authorization.

The OS-protected SIGNING_TRUST port holds one immutable event per local trust
decision and a CAS head. A missing, corrupt or incomplete chain denies use.
The caller authenticates human actions; package bytes alone can never add trust.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass

from ..domain_contracts import is_uuid_v7
from ..plugin_grant_repository import SqlitePluginGrantRepository, _actor
from ..ports.credential_store import (
    CredentialStore,
    SecretAccessContext,
    SecretAccessDenied,
    SecretConflict,
    SecretCorrupt,
    SecretKind,
    SecretNotFound,
    SecretPurpose,
    SecretReference,
    SecretUnavailable,
)
from .plugin_grants import PluginEnableConfirmation, PluginGrantActor, PluginGrantProblem
from .plugin_manifest import (
    PluginInvocationPlan,
    PluginInvocationRequest,
    PluginProjectGrant,
    VerifiedPluginPackage,
    authorize_plugin_invocation,
    verify_plugin_package,
)

_KEY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")
_TRACE = re.compile(r"[0-9a-f]{32}\Z")
_HEX_KEY = re.compile(r"[0-9a-f]{64}\Z")
_MAX_EVENTS = 1024


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class PluginTrustDecision:
    """Exact, explicit local trust review from the authenticated native caller."""

    action_id: str
    publisher_key_id: str
    public_key_sha256: str
    expected_revision: int | None
    operation: str  # trust, revoke, or rotate after revoke
    previous_key_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class PluginPublisherTrustEvent:
    revision: int
    operation: str
    action_id: str
    publisher_key_id: str
    public_key_sha256: str
    actor_id: str
    occurred_at: str
    event_sha256: str


@dataclass(frozen=True, slots=True)
class PluginPublisherTrustState:
    publisher_key_id: str
    revision: int
    status: str
    public_key_sha256: str


class PluginPublisherTrustStore:
    """Durable publisher authority shared across all projects in one profile."""

    def __init__(self, credentials: CredentialStore, profile_id: str) -> None:
        if not isinstance(profile_id, str):
            raise ValueError("plugin-publisher-profile-invalid")
        # SecretReference validates profile scope without creating a record.
        SecretReference(profile_id, SecretKind.SIGNING_TRUST, "plugin-publisher-check", "head")
        self._credentials = credentials
        self._profile_id = profile_id

    def _reference(self, key_id: str, revision: int | None) -> SecretReference:
        if _KEY_ID.fullmatch(key_id) is None:
            raise PluginGrantProblem("plugin-publisher-key-id-invalid")
        subject = "plugin-publisher-" + hashlib.sha256(key_id.encode("ascii")).hexdigest()
        name = "head" if revision is None else f"event-{revision:06d}"
        return SecretReference(self._profile_id, SecretKind.SIGNING_TRUST, subject, name)

    @staticmethod
    def _context(trace_id: str) -> SecretAccessContext:
        if not isinstance(trace_id, str) or _TRACE.fullmatch(trace_id) is None:
            raise PluginGrantProblem("plugin-publisher-context-invalid")
        return SecretAccessContext("CAP-04.S05", SecretPurpose.SIGNING_VERIFICATION, trace_id)

    def _read(self, reference: SecretReference, context: SecretAccessContext) -> tuple[str, bytes] | None:
        try:
            record, lease = self._credentials.lease_record(reference, context)
            with lease:
                return record.version, lease.use(bytes)
        except SecretNotFound:
            return None
        except SecretCorrupt:
            raise PluginGrantProblem("plugin-publisher-corrupt") from None
        except SecretUnavailable, SecretAccessDenied:
            raise PluginGrantProblem("plugin-publisher-unavailable") from None

    @staticmethod
    def _decode(raw: bytes) -> dict[str, object]:
        try:
            value = json.loads(raw.decode("ascii"))
            if not isinstance(value, dict) or _canonical(value) != raw:
                raise ValueError
            return value
        except UnicodeError, ValueError, TypeError, RecursionError:
            raise PluginGrantProblem("plugin-publisher-corrupt") from None

    def _load(self, key_id: str, trace_id: str) -> tuple[str | None, list[dict[str, object]], dict[str, object] | None]:
        context = self._context(trace_id)
        head_result = self._read(self._reference(key_id, None), context)
        head_version: str | None = None
        head: dict[str, object] | None = None
        if head_result is not None:
            head_version, raw = head_result
            head = self._decode(raw)
            if (
                set(head) != {"schemaVersion", "publisherKeyId", "revision", "eventSha256"}
                or head["schemaVersion"] != "1.0"
                or head["publisherKeyId"] != key_id
                or type(head["revision"]) is not int
                or not 1 <= head["revision"] <= _MAX_EVENTS
                or not isinstance(head["eventSha256"], str)
                or _SHA.fullmatch(head["eventSha256"]) is None
            ):
                raise PluginGrantProblem("plugin-publisher-corrupt")
        committed = int(head["revision"]) if head is not None else 0
        events: list[dict[str, object]] = []
        predecessor: str | None = None
        for revision in range(1, committed + 2):
            event_result = self._read(self._reference(key_id, revision), context)
            if event_result is None:
                if revision <= committed:
                    raise PluginGrantProblem("plugin-publisher-corrupt")
                return head_version, events, None
            _version, raw = event_result
            event = self._decode(raw)
            if (
                set(event)
                != {
                    "schemaVersion",
                    "publisherKeyId",
                    "revision",
                    "operation",
                    "actionId",
                    "publicKey",
                    "publicKeySha256",
                    "previousKeySha256",
                    "expectedRevision",
                    "predecessorSha256",
                    "actorId",
                    "traceId",
                    "occurredAt",
                }
                or event["schemaVersion"] != "1.0"
                or event["publisherKeyId"] != key_id
                or event["revision"] != revision
                or event["operation"] not in {"trust", "revoke", "rotate"}
                or not isinstance(event["actionId"], str)
                or not is_uuid_v7(event["actionId"])
                or not isinstance(event["actorId"], str)
                or not is_uuid_v7(event["actorId"])
                or not isinstance(event["traceId"], str)
                or _TRACE.fullmatch(event["traceId"]) is None
                or not isinstance(event["occurredAt"], str)
                or not isinstance(event["publicKey"], str)
                or _HEX_KEY.fullmatch(event["publicKey"]) is None
                or event["publicKeySha256"] != _sha(bytes.fromhex(event["publicKey"]))
                or event["expectedRevision"] != (revision - 1 or None)
                or event["predecessorSha256"] != predecessor
                or (
                    event["previousKeySha256"] is not None
                    and (
                        not isinstance(event["previousKeySha256"], str)
                        or _SHA.fullmatch(event["previousKeySha256"]) is None
                    )
                )
            ):
                raise PluginGrantProblem("plugin-publisher-corrupt")
            predecessor = _sha(raw)
            if revision <= committed:
                if revision == committed and head is not None and predecessor != head["eventSha256"]:
                    raise PluginGrantProblem("plugin-publisher-corrupt")
                events.append(event)
                continue
            return head_version, events, event
        raise PluginGrantProblem("plugin-publisher-corrupt")

    def _state(self, key_id: str, trace_id: str) -> tuple[str | None, list[dict[str, object]]]:
        head_version, events, pending = self._load(key_id, trace_id)
        if pending is not None:
            raise PluginGrantProblem("plugin-publisher-incomplete")
        if events:
            # Recheck the authenticated head tip, including deletion/rollback.
            head_result = self._read(self._reference(key_id, None), self._context(trace_id))
            if (
                head_result is None
                or head_result[0] != head_version
                or self._decode(head_result[1])["eventSha256"] != _sha(_canonical(events[-1]))
            ):
                raise PluginGrantProblem("plugin-publisher-corrupt")
        return head_version, events

    @staticmethod
    def _project(event: dict[str, object]) -> PluginPublisherTrustState:
        return PluginPublisherTrustState(
            publisher_key_id=str(event["publisherKeyId"]),
            revision=int(event["revision"]),
            status="revoked" if event["operation"] == "revoke" else "active",
            public_key_sha256=str(event["publicKeySha256"]),
        )

    def state(self, key_id: str, *, audit_context: str) -> PluginPublisherTrustState | None:
        _version, events = self._state(key_id, audit_context)
        return self._project(events[-1]) if events else None

    def history(self, key_id: str, *, audit_context: str) -> tuple[PluginPublisherTrustEvent, ...]:
        _version, events = self._state(key_id, audit_context)
        return tuple(
            PluginPublisherTrustEvent(
                int(event["revision"]),
                str(event["operation"]),
                str(event["actionId"]),
                str(event["publisherKeyId"]),
                str(event["publicKeySha256"]),
                str(event["actorId"]),
                str(event["occurredAt"]),
                _sha(_canonical(event)),
            )
            for event in events
        )

    def active_key(self, key_id: str, *, audit_context: str) -> bytes:
        key, _state = self.active_authority(key_id, audit_context=audit_context)
        return key

    def active_authority(self, key_id: str, *, audit_context: str) -> tuple[bytes, PluginPublisherTrustState]:
        _version, events = self._state(key_id, audit_context)
        if not events:
            raise PluginGrantProblem("plugin-publisher-untrusted")
        if events[-1]["operation"] == "revoke":
            raise PluginGrantProblem("plugin-publisher-revoked")
        return bytes.fromhex(str(events[-1]["publicKey"])), self._project(events[-1])

    def decide(
        self, public_key: bytes | None, decision: PluginTrustDecision, *, actor: PluginGrantActor
    ) -> PluginPublisherTrustState:
        _actor(actor)
        if (
            not isinstance(decision, PluginTrustDecision)
            or not is_uuid_v7(decision.action_id)
            or not isinstance(decision.publisher_key_id, str)
            or _KEY_ID.fullmatch(decision.publisher_key_id) is None
            or not isinstance(decision.public_key_sha256, str)
            or _SHA.fullmatch(decision.public_key_sha256) is None
            or decision.operation not in {"trust", "revoke", "rotate"}
            or (
                decision.expected_revision is not None
                and (type(decision.expected_revision) is not int or decision.expected_revision < 1)
            )
            or (
                decision.previous_key_sha256 is not None
                and (
                    not isinstance(decision.previous_key_sha256, str)
                    or _SHA.fullmatch(decision.previous_key_sha256) is None
                )
            )
        ):
            raise PluginGrantProblem("plugin-publisher-decision-invalid")
        if decision.operation in {"trust", "rotate"}:
            if (
                not isinstance(public_key, bytes)
                or len(public_key) != 32
                or _sha(public_key) != decision.public_key_sha256
            ):
                raise PluginGrantProblem("plugin-publisher-confirmation-mismatch")
        elif public_key is not None:
            raise PluginGrantProblem("plugin-publisher-decision-invalid")
        head_version, events, pending = self._load(decision.publisher_key_id, actor.trace_id)
        prior = events[-1] if events else None
        prior_revision = int(prior["revision"]) if prior is not None else None
        if (prior_revision or 0) >= _MAX_EVENTS:
            raise PluginGrantProblem("plugin-publisher-history-limit")
        for event in events:
            if event["actionId"] == decision.action_id:
                if pending is not None:
                    raise PluginGrantProblem("plugin-publisher-incomplete")
                if event is prior and self._decision_matches(event, decision, actor):
                    return self._project(event)
                raise PluginGrantProblem("plugin-publisher-action-conflict")
        if prior_revision != decision.expected_revision:
            raise PluginGrantProblem("plugin-publisher-stale-revision")
        if decision.operation == "trust":
            if prior is not None and prior["operation"] != "revoke":
                raise PluginGrantProblem("plugin-publisher-collision")
            if prior is not None and prior["publicKeySha256"] != decision.public_key_sha256:
                raise PluginGrantProblem("plugin-publisher-rotation-required")
            if decision.previous_key_sha256 is not None:
                raise PluginGrantProblem("plugin-publisher-decision-invalid")
        elif decision.operation == "rotate":
            if (
                prior is None
                or prior["operation"] != "revoke"
                or decision.previous_key_sha256 != prior["publicKeySha256"]
                or decision.public_key_sha256 == prior["publicKeySha256"]
            ):
                raise PluginGrantProblem("plugin-publisher-rotation-denied")
        else:
            if (
                prior is None
                or prior["operation"] == "revoke"
                or decision.public_key_sha256 != prior["publicKeySha256"]
                or decision.previous_key_sha256 is not None
            ):
                raise PluginGrantProblem("plugin-publisher-revoke-denied")
            public_key = bytes.fromhex(str(prior["publicKey"]))
        assert isinstance(public_key, bytes)
        next_event = {
            "schemaVersion": "1.0",
            "publisherKeyId": decision.publisher_key_id,
            "revision": (prior_revision or 0) + 1,
            "operation": decision.operation,
            "actionId": decision.action_id,
            "publicKey": public_key.hex(),
            "publicKeySha256": decision.public_key_sha256,
            "previousKeySha256": decision.previous_key_sha256,
            "expectedRevision": decision.expected_revision,
            "predecessorSha256": _sha(_canonical(prior)) if prior is not None else None,
            "actorId": actor.actor_id,
            "traceId": actor.trace_id,
            "occurredAt": actor.occurred_at,
        }
        if pending is not None and pending != next_event:
            raise PluginGrantProblem("plugin-publisher-incomplete")
        context = self._context(actor.trace_id)
        if pending is None:
            try:
                self._credentials.put(
                    self._reference(decision.publisher_key_id, int(next_event["revision"])),
                    _canonical(next_event),
                    context,
                )
            except SecretConflict:
                raise PluginGrantProblem("plugin-publisher-conflict") from None
            except SecretUnavailable, SecretAccessDenied, SecretCorrupt:
                raise PluginGrantProblem("plugin-publisher-unavailable") from None
        head = {
            "schemaVersion": "1.0",
            "publisherKeyId": decision.publisher_key_id,
            "revision": next_event["revision"],
            "eventSha256": _sha(_canonical(next_event)),
        }
        try:
            self._credentials.put(
                self._reference(decision.publisher_key_id, None),
                _canonical(head),
                context,
                expected_version=head_version,
            )
        except SecretConflict:
            raise PluginGrantProblem("plugin-publisher-conflict") from None
        except SecretUnavailable, SecretAccessDenied, SecretCorrupt:
            raise PluginGrantProblem("plugin-publisher-unavailable") from None
        return self._project(next_event)

    @staticmethod
    def _decision_matches(event: dict[str, object], decision: PluginTrustDecision, actor: PluginGrantActor) -> bool:
        return (
            event["publisherKeyId"] == decision.publisher_key_id
            and event["operation"] == decision.operation
            and event["publicKeySha256"] == decision.public_key_sha256
            and event["expectedRevision"] == decision.expected_revision
            and event["previousKeySha256"] == decision.previous_key_sha256
            and event["actorId"] == actor.actor_id
        )

    def verify_package_with_authority(
        self, manifest_bytes: bytes, signature: bytes, package_files: Mapping[str, bytes], *, audit_context: str
    ) -> tuple[VerifiedPluginPackage, PluginPublisherTrustState]:
        # This preliminary parse only selects a local key. The T01 verifier
        # repeats strict duplicate-key, signature, manifest and file checks.
        try:
            if not isinstance(manifest_bytes, bytes) or not 0 < len(manifest_bytes) <= 64 * 1024:
                raise ValueError
            document = json.loads(manifest_bytes)
            key_id = document["publisherKeyId"]
            if not isinstance(key_id, str):
                raise ValueError
        except ValueError, TypeError, KeyError, UnicodeError, RecursionError:
            raise PluginGrantProblem("plugin-package-invalid") from None
        key, authority = self.active_authority(key_id, audit_context=audit_context)
        try:
            return verify_plugin_package(manifest_bytes, signature, package_files, {key_id: key}), authority
        except ValueError, TypeError:
            raise PluginGrantProblem("plugin-package-invalid") from None

    def verify_package(
        self, manifest_bytes: bytes, signature: bytes, package_files: Mapping[str, bytes], *, audit_context: str
    ) -> VerifiedPluginPackage:
        package, _authority = self.verify_package_with_authority(
            manifest_bytes, signature, package_files, audit_context=audit_context
        )
        return package


class PluginGrantService:
    """Composition boundary: local trust plus exact current project authority."""

    def __init__(self, trust: PluginPublisherTrustStore, grants: SqlitePluginGrantRepository) -> None:
        self._trust = trust
        self._grants = grants

    def enable(
        self,
        manifest_bytes: bytes,
        signature: bytes,
        package_files: Mapping[str, bytes],
        confirmation: PluginEnableConfirmation,
        *,
        actor: PluginGrantActor,
    ) -> PluginProjectGrant:
        _actor(actor)
        if not isinstance(confirmation, PluginEnableConfirmation):
            raise PluginGrantProblem("plugin-grant-confirmation-invalid")
        try:
            package, trust = self._trust.verify_package_with_authority(
                manifest_bytes, signature, package_files, audit_context=actor.trace_id
            )
        except PluginGrantProblem as error:
            self._grants.record_denial(plugin_id=confirmation.plugin_id, reason_code=error.code, actor=actor)
            raise
        return self._grants.enable(
            package, confirmation, actor=actor,
            trusted_key_sha256=trust.public_key_sha256,
            trusted_key_revision=trust.revision,
        )

    def current_authorization(
        self,
        manifest_bytes: bytes,
        signature: bytes,
        package_files: Mapping[str, bytes],
        request: PluginInvocationRequest,
        *,
        expected_plugin_id: str,
        actor: PluginGrantActor,
    ) -> PluginInvocationPlan:
        """Call at every dispatch, including retries and every project switch."""
        _actor(actor, allow_system=True)
        if not isinstance(request, PluginInvocationRequest):
            raise PluginGrantProblem("plugin-invocation-invalid")
        try:
            package, trust = self._trust.verify_package_with_authority(
                manifest_bytes, signature, package_files, audit_context=actor.trace_id
            )
            if package.manifest.plugin_id != expected_plugin_id:
                raise PluginGrantProblem("plugin-package-identity-mismatch")
            authority = self._grants.current_grant_authority(expected_plugin_id)
            if authority is None:
                raise PluginGrantProblem("plugin-grant-not-active")
            if (
                authority.trusted_key_sha256 != trust.public_key_sha256
                or authority.trusted_key_revision != trust.revision
            ):
                raise PluginGrantProblem("plugin-grant-trust-changed")
            try:
                return authorize_plugin_invocation(package, authority.grant, request)
            except ValueError:
                raise PluginGrantProblem("plugin-invocation-denied") from None
        except PluginGrantProblem as error:
            self._grants.record_denial(
                plugin_id=expected_plugin_id,
                reason_code=error.code,
                actor=actor,
                invocation_id=request.invocation_id,
            )
            raise
