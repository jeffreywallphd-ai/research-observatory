"""Pure, source/copy-specific permitted-use decisions.

The caller obtains the current policy from protected project storage and supplies
trusted action time after its project, actor, Intent and privacy checks. These
models are values, not an authority to read a copy, execute an action or egress.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .connectors.contracts import SourceTerms
from .ingestion.import_drafts import Digest, DraftValue, Identity, ProjectIdentity
from .reconciliation.contracts import SourceAddress

type RightsAction = Literal["store", "inspect", "index", "derive", "model-use", "quote", "export", "share"]
type ResourceClass = Literal["metadata", "full-text", "derived-text", "embedding"]
type CopyLocation = Literal["local-project-object", "local-source", "provider-hosted", "collaboration-copy"]
type PermissionValue = Literal["permitted", "denied", "unknown"]
type DecisionCode = Literal["allow", "deny", "unknown", "require-confirmation"]
type AuthorityKind = Literal["policy", "legacy-import-bridge", "none"]
type DestinationKind = Literal["local-project", "local-export", "remote-model", "external-export", "collaboration"]
type ProvenanceBasis = Literal["source-observation", "researcher-confirmed", "verified-entitlement"]
type Confidence = Literal["reported", "confirmed", "verified", "disputed"]

Code = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")]
UtcMillis = Annotated[str, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$")]


def _instant(value: str) -> datetime:
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z", value) is None:
        raise ValueError("rights-invalid-time")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError("rights-invalid-time") from error


class RightsSubject(DraftValue):
    """An exact retained record assertion and opaque copy, never a Work grant."""

    project_id: ProjectIdentity
    source_assertion_revision_id: Identity
    address: SourceAddress
    copy_id: Identity
    copy_location: CopyLocation
    resource_class: ResourceClass


class RightsUse(DraftValue):
    """One action and an exact purpose/destination; there are no wildcards."""

    action: RightsAction
    purpose: Code
    destination_kind: DestinationKind
    provider: Code | None = None
    region: Code | None = None
    share_group: Code | None = None

    @model_validator(mode="after")
    def coherent_destination(self) -> Self:
        for code in (self.purpose, self.provider, self.region, self.share_group):
            if code is not None and re.fullmatch(r"[a-z][a-z0-9-]{0,63}", code) is None:
                raise ValueError("rights-context-code-invalid")
        local_actions = {"store", "inspect", "index", "derive", "quote"}
        if self.action in local_actions and self.destination_kind != "local-project":
            raise ValueError("rights-action-destination-mismatch")
        if self.action == "model-use" and self.destination_kind not in {"local-project", "remote-model"}:
            raise ValueError("rights-action-destination-mismatch")
        if self.action == "export" and self.destination_kind not in {"local-export", "external-export"}:
            raise ValueError("rights-action-destination-mismatch")
        if self.action == "share" and self.destination_kind != "collaboration":
            raise ValueError("rights-action-destination-mismatch")
        if self.destination_kind in {"remote-model", "external-export"}:
            if self.provider is None or self.region is None or self.share_group is not None:
                raise ValueError("rights-destination-context-incomplete")
        elif self.destination_kind == "collaboration":
            if self.share_group is None or self.provider is not None or self.region is not None:
                raise ValueError("rights-destination-context-incomplete")
        elif any(value is not None for value in (self.provider, self.region, self.share_group)):
            raise ValueError("rights-destination-context-unexpected")
        return self


class RightsPermission(DraftValue):
    """One provenance-bearing observation or explicit permission assertion."""

    assertion_id: Identity
    subject: RightsSubject
    use: RightsUse
    value: PermissionValue
    basis: ProvenanceBasis
    confidence: Confidence
    asserted_by_actor_id: Identity | None
    grantee_actor_id: Identity | None = None
    evidence_revision_ids: tuple[Identity, ...] = Field(max_length=16)
    license_observation_revision_id: Identity | None
    entitlement_revision_id: Identity | None
    recorded_at: UtcMillis
    expires_at: UtcMillis | None
    confirmation_required: bool = False

    @model_validator(mode="after")
    def bounded_provenance(self) -> Self:
        recorded_at = _instant(self.recorded_at)
        if self.expires_at is not None and _instant(self.expires_at) <= recorded_at:
            raise ValueError("rights-expiry-before-recorded")
        if len(set(self.evidence_revision_ids)) != len(self.evidence_revision_ids):
            raise ValueError("rights-duplicate-evidence")
        if self.value != "unknown" and not self.evidence_revision_ids:
            raise ValueError("rights-evidence-required")
        if self.basis == "source-observation":
            if (
                self.asserted_by_actor_id is not None
                or self.entitlement_revision_id is not None
                or self.confidence not in {"reported", "disputed"}
                or self.confirmation_required
            ):
                raise ValueError("rights-observation-is-not-grant")
        elif self.basis == "researcher-confirmed":
            if (
                self.asserted_by_actor_id is None
                or self.entitlement_revision_id is not None
                or self.confidence != "confirmed"
            ):
                raise ValueError("rights-confirmation-provenance-invalid")
        elif self.asserted_by_actor_id is None or self.entitlement_revision_id is None or self.confidence != "verified":
            raise ValueError("rights-entitlement-provenance-invalid")
        if self.confirmation_required and self.value != "permitted":
            raise ValueError("rights-confirmation-requires-permission")
        return self


class RightsSourceObservation(DraftValue):
    """Exact source-reported terms; never an action permission or entitlement."""

    project_id: ProjectIdentity
    source_assertion_revision_id: Identity
    address: SourceAddress
    source_revision_id: Identity
    source_sha256: Digest
    provider: Code
    terms: SourceTerms = Field(repr=False)
    retrieved_at: UtcMillis | None

    @model_validator(mode="after")
    def bounded_source(self) -> Self:
        if self.address.kind == "connector-record" and (
            self.source_revision_id != self.address.revision_id or self.retrieved_at is None
        ):
            raise ValueError("rights-observation-source-mismatch")
        if self.retrieved_at is not None:
            _instant(self.retrieved_at)
        return self


class RightsPolicyRevision(DraftValue):
    """Current immutable policy revision for exactly one source/copy/resource."""

    schema_version: Literal["1.0"] = "1.0"
    contract_version: Literal["1.0.0"] = "1.0.0"
    document_type: Literal["research-observatory-rights-policy-revision"] = (
        "research-observatory-rights-policy-revision"
    )
    revision_id: Identity
    predecessor_revision_id: Identity | None
    subject: RightsSubject
    source_observation: RightsSourceObservation | None = None
    permissions: tuple[RightsPermission, ...] = Field(max_length=256)

    @model_validator(mode="after")
    def one_subject_unique_assertions(self) -> Self:
        if self.predecessor_revision_id == self.revision_id:
            raise ValueError("rights-revision-self-predecessor")
        if any(item.subject != self.subject for item in self.permissions):
            raise ValueError("rights-mixed-subject-policy")
        observation = self.source_observation
        if observation is not None and (
            observation.project_id != self.subject.project_id
            or observation.source_assertion_revision_id != self.subject.source_assertion_revision_id
            or observation.address != self.subject.address
        ):
            raise ValueError("rights-observation-subject-mismatch")
        ids = [item.assertion_id for item in self.permissions]
        if len(set(ids)) != len(ids):
            raise ValueError("rights-duplicate-assertion")
        return self


class RightsRequest(DraftValue):
    """Requested use; current policy and trusted time cannot be caller claims."""

    actor_id: Identity
    subject: RightsSubject
    use: RightsUse


class RightsDecision(DraftValue):
    schema_version: Literal["1.0"] = "1.0"
    contract_version: Literal["1.0.0"] = "1.0.0"
    document_type: Literal["research-observatory-rights-decision"] = "research-observatory-rights-decision"
    code: DecisionCode
    reason_code: Code
    authority_kind: AuthorityKind
    actor_id: Identity
    subject: RightsSubject
    use: RightsUse
    policy_revision_id: Identity | None
    governing_assertion_ids: tuple[Identity, ...] = Field(max_length=256)
    source_assertion_sha256: Digest | None
    evaluated_at: UtcMillis
    expires_at: UtcMillis | None

    @model_validator(mode="after")
    def bounded_historical_decision(self) -> Self:
        evaluated_at = _instant(self.evaluated_at)
        expires_at = _instant(self.expires_at) if self.expires_at is not None else None
        if re.fullmatch(r"[a-z][a-z0-9-]{0,63}", self.reason_code) is None:
            raise ValueError("rights-decision-reason-invalid")
        if tuple(sorted(set(self.governing_assertion_ids))) != self.governing_assertion_ids:
            raise ValueError("rights-decision-assertions-invalid")
        if (self.authority_kind == "policy") != (self.policy_revision_id is not None):
            raise ValueError("rights-decision-authority-invalid")
        if self.authority_kind == "legacy-import-bridge" and (
            self.code != "allow"
            or self.reason_code != "rights-legacy-import-confirmed"
            or self.governing_assertion_ids != (self.subject.source_assertion_revision_id,)
            or self.source_assertion_sha256 is None
            or self.subject.address.kind != "import-member"
            or self.subject.copy_id != self.subject.source_assertion_revision_id
            or self.subject.copy_location != "local-source"
            or self.subject.resource_class != "metadata"
            or self.use.action not in {"store", "inspect", "derive", "index"}
            or self.use.purpose != "corpus-membership"
            or self.use.destination_kind != "local-project"
            or self.expires_at is not None
        ):
            raise ValueError("rights-legacy-bridge-witness-invalid")
        if self.code == "allow" and (
            self.authority_kind == "none"
            or not self.governing_assertion_ids
            or (expires_at is not None and expires_at <= evaluated_at)
        ):
            raise ValueError("rights-decision-witness-invalid")
        return self


def evaluate_rights(
    policy: RightsPolicyRevision | None,
    request: RightsRequest,
    *,
    now: datetime,
) -> RightsDecision:
    """Evaluate an exact current snapshot; only ``allow`` permits an action.

    The caller must load ``policy`` by the request's exact subject from protected
    storage inside the action transaction and supply a trusted clock. A historical
    decision is an audit fact, never a reusable permission witness.
    """

    request = RightsRequest.model_validate(request)
    policy = RightsPolicyRevision.model_validate(policy) if policy is not None else None
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("rights-trusted-time-required")
    at = now.astimezone(UTC)
    evaluated_at = at.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    code: DecisionCode = "unknown"
    reason = "rights-policy-missing"
    matched: tuple[RightsPermission, ...] = ()
    if policy is not None:
        if policy.subject != request.subject:
            reason = "rights-policy-subject-mismatch"
        else:
            matched = tuple(
                item
                for item in policy.permissions
                if item.use == request.use
                and (item.grantee_actor_id is None or item.grantee_actor_id == request.actor_id)
            )
            if not matched:
                reason = "rights-assertion-missing"
            elif any(item.value == "denied" for item in matched):
                code, reason = "deny", "rights-explicit-denial"
            elif any(item.expires_at is not None and _instant(item.expires_at) <= at for item in matched):
                code, reason = "deny", "rights-assertion-expired"
            elif any(_instant(item.recorded_at) > at for item in matched):
                reason = "rights-assertion-not-effective"
            elif any(item.value == "unknown" for item in matched):
                reason = "rights-assertion-unknown"
            elif any(item.confidence == "disputed" for item in matched):
                code, reason = "require-confirmation", "rights-disputed-assertion"
            else:
                grants = tuple(
                    item for item in matched if item.value == "permitted" and item.basis != "source-observation"
                )
                if not grants:
                    reason = "rights-observation-only"
                elif any(item.confirmation_required for item in grants):
                    code, reason = "require-confirmation", "rights-confirmation-required"
                else:
                    code, reason = "allow", "rights-explicit-permission"
    expiry = min((item.expires_at for item in matched if item.expires_at is not None), default=None)
    return RightsDecision(
        code=code,
        reason_code=reason,
        authority_kind="policy" if policy is not None else "none",
        actor_id=request.actor_id,
        subject=request.subject,
        use=request.use,
        policy_revision_id=policy.revision_id if policy is not None else None,
        governing_assertion_ids=tuple(sorted(item.assertion_id for item in matched)),
        source_assertion_sha256=None,
        evaluated_at=evaluated_at,
        expires_at=expiry,
    )
