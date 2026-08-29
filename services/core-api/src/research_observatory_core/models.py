"""Portable response models for the runtime service surface."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import CORE_API_SCHEMA_VERSION, CORE_API_VERSION, CORE_SERVICE_ID


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.capitalize() for part in rest)


class ContractModel(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True, extra="forbid", frozen=True)


class RuntimeState(StrEnum):
    STARTING = "starting"
    READY = "ready"
    STOPPING = "stopping"
    UNAVAILABLE = "unavailable"


class ProjectLifecycleState(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    TRASH = "trash"


class ProjectAccessMode(StrEnum):
    CLOSED = "closed"
    READ_WRITE = "read-write"
    READ_ONLY = "read-only"


class ProjectCompatibilityState(StrEnum):
    COMPATIBLE = "compatible"
    MIGRATION_REQUIRED = "migration-required"
    NEWER_UNSUPPORTED = "newer-unsupported"


class ProjectRecoveryAction(StrEnum):
    NONE = "none"
    BACKUP_THEN_MIGRATE = "backup-then-migrate"
    BACKUP_THEN_USE_COMPATIBLE_APPLICATION = "backup-then-use-compatible-application"


class PrivacyNetworkPolicy(StrEnum):
    OFFLINE = "offline"
    METADATA_ONLY = "metadata-only"
    APPROVED_PROVIDERS = "approved-providers"


class RemoteModelApproval(StrEnum):
    PREVIEW_EVERY_TASK = "preview-every-task"


class TelemetryMode(StrEnum):
    OFF = "off"
    LOCAL_DIAGNOSTICS_ONLY = "local-diagnostics-only"


class DocumentRetentionPolicy(StrEnum):
    PROJECT_LIFETIME = "project-lifetime"
    REVIEW_AFTER_90_DAYS = "review-after-90-days"
    REVIEW_AFTER_365_DAYS = "review-after-365-days"


class EgressEnforcement(StrEnum):
    DENY = "deny"
    REQUIRE_TASK_PREVIEW = "require-task-preview"


class CacheClearState(StrEnum):
    CLEARED = "cleared"
    CLEARED_CLEANUP_PENDING = "cleared-cleanup-pending"


class RuntimeProjection(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    service: str = CORE_SERVICE_ID
    version: str = CORE_API_VERSION
    state: RuntimeState
    capabilities: tuple[str, ...]


class HealthResponse(RuntimeProjection):
    alive: bool = True


class ReadinessResponse(RuntimeProjection):
    ready: bool


class VersionResponse(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    service: str = CORE_SERVICE_ID
    version: str = CORE_API_VERSION
    api_version: str = "1.0.0"
    minimum_client_api_version: str = "1.0.0"
    maximum_client_api_version_exclusive: str = "2.0.0"


class ConfigurationResponse(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    profile: str
    bind_host: str
    bind_port: str


class ModuleResponse(ContractModel):
    module_id: str
    capabilities: tuple[str, ...]


class ModulesResponse(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    modules: tuple[ModuleResponse, ...]


class CapabilitiesResponse(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    capabilities: tuple[str, ...] = Field(min_length=1)


class ProblemDetail(ContractModel):
    type: str = Field(pattern=r"^urn:research-observatory:problem:[a-z0-9-]+$")
    title: str = Field(min_length=1, max_length=120)
    status: int = Field(ge=400, le=599)
    detail: str = Field(min_length=1, max_length=500)
    code: str = Field(pattern=r"^RO-CORE-[A-Z0-9-]+$")
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    retryable: bool
    remediation: str = Field(min_length=1, max_length=240)


class ProjectCreateRequest(ContractModel):
    parent_directory: str = Field(min_length=1, max_length=4096)
    directory_name: str = Field(pattern=r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
    display_name: str = Field(min_length=1, max_length=120)
    template_id: str = Field(pattern=r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$")


class ProjectRootRequest(ContractModel):
    root: str = Field(min_length=1, max_length=4096)


class ProvenanceLineageRequest(ProjectRootRequest):
    revision_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    direction: Literal["ancestors", "descendants"]
    cursor: int = Field(default=0, ge=0, le=10_000)
    page_size: int = Field(default=50, ge=1, le=100)
    max_depth: int = Field(default=8, ge=1, le=16)


class ProvenanceLineageNode(ContractModel):
    revision_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    entity_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    entity_kind: str = Field(pattern=r"^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+){0,15}$", max_length=128)
    depth: int = Field(ge=0, le=16)
    event_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    event_type: str = Field(pattern=r"^org\.research-observatory\..+\.v[1-9][0-9]{0,5}$", max_length=160)
    activity_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    activity_type: str = Field(pattern=r"^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+){0,15}$", max_length=128)
    activity_status: Literal["succeeded", "failed", "cancelled", "denied"]
    configuration_id: str = Field(pattern=r"^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+){0,15}$", max_length=128)
    configuration_version: str = Field(pattern=r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$", max_length=29)
    configuration_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    agent_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    agent_type: Literal["human", "model", "software", "system"]
    agent_role: str = Field(pattern=r"^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+){0,15}$", max_length=128)
    occurred_at: str


class ProvenanceLineagePage(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    revision_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    direction: Literal["ancestors", "descendants"]
    items: tuple[ProvenanceLineageNode, ...] = Field(max_length=100)
    missing_revision_ids: tuple[str, ...] = Field(max_length=256)
    next_cursor: int | None = Field(default=None, ge=0, le=10_000)
    integrity_state: Literal["verified", "integrity-review"]
    legacy_event_count: int = Field(ge=0, le=9_007_199_254_740_991)


class ProjectDeleteRequest(ProjectRootRequest):
    confirmation: str = Field(min_length=1, max_length=80)


class ProjectProjection(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    project_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    display_name: str = Field(min_length=1, max_length=120)
    template_id: str = Field(pattern=r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$")
    lifecycle_state: ProjectLifecycleState
    root: str = Field(min_length=1, max_length=4096)
    open: bool
    access_mode: ProjectAccessMode
    compatibility_state: ProjectCompatibilityState
    package_format_version: str = Field(
        pattern=(
            r"^(?:0|[1-9][0-9]{0,14}|[1-8][0-9]{15}|900719925474099[01])\."
            r"(?:0|[1-9][0-9]{0,14}|[1-8][0-9]{15}|900719925474099[01])\."
            r"(?:0|[1-9][0-9]{0,14}|[1-8][0-9]{15}|900719925474099[01])$"
        )
    )
    backup_required_before_repair: bool
    recovery_action: ProjectRecoveryAction
    revision: int = Field(ge=0, le=9_007_199_254_740_991)
    delete_confirmation: str = Field(pattern=r"^delete:[0-9a-f-]{36}$")

    @model_validator(mode="after")
    def validate_safe_open_state(self) -> ProjectProjection:
        if self.delete_confirmation != f"delete:{self.project_id}":
            raise ValueError("project deletion confirmation must match the project identity")
        if self.open != (self.access_mode is not ProjectAccessMode.CLOSED):
            raise ValueError("project open state must match its access mode")
        if (
            self.lifecycle_state is not ProjectLifecycleState.ACTIVE
            and self.access_mode is not ProjectAccessMode.CLOSED
        ):
            raise ValueError("only active projects may be open")
        if self.compatibility_state is ProjectCompatibilityState.COMPATIBLE:
            if self.package_format_version != "1.0.0":
                raise ValueError("compatible projects must use the current package format")
            if self.access_mode is ProjectAccessMode.READ_ONLY:
                raise ValueError("compatible projects do not use compatibility read-only mode")
            if self.backup_required_before_repair or self.recovery_action is not ProjectRecoveryAction.NONE:
                raise ValueError("compatible projects do not require compatibility repair")
        elif self.compatibility_state is ProjectCompatibilityState.MIGRATION_REQUIRED:
            if self.access_mode is ProjectAccessMode.READ_WRITE:
                raise ValueError("incompatible projects cannot open for write")
            if (
                not self.backup_required_before_repair
                or self.recovery_action is not ProjectRecoveryAction.BACKUP_THEN_MIGRATE
            ):
                raise ValueError("migration-required projects require the backup-then-migrate action")
        else:
            if self.access_mode is ProjectAccessMode.READ_WRITE:
                raise ValueError("incompatible projects cannot open for write")
            if (
                not self.backup_required_before_repair
                or self.recovery_action is not ProjectRecoveryAction.BACKUP_THEN_USE_COMPATIBLE_APPLICATION
            ):
                raise ValueError("newer-unsupported projects require the backup-then-use-compatible-application action")
        return self


IntentPrimaryUseCase = Literal[
    "rapid-orientation",
    "systematic-review",
    "living-review",
    "theory-synthesis",
    "hermeneutic-inquiry",
    "critical-problematization",
    "technical-landscape",
    "novelty-audit",
    "empirical-study-design",
    "empirical-study-to-article",
    "empirical-results-to-article",
    "theory-article-development",
    "critical-article-development",
    "manuscript-review-revision",
]
IntentEpistemicMode = Literal["systematic", "theory", "technical", "hermeneutic", "critical", "novelty", "empirical"]
IntentSourceKind = Literal[
    "peer-reviewed-article",
    "conference-paper",
    "book",
    "chapter",
    "preprint",
    "technical-report",
    "dataset",
    "standard",
    "patent",
    "thesis",
    "web-resource",
    "private-report",
]
IntentEvidenceType = Literal[
    "empirical-study",
    "systematic-review",
    "theoretical-work",
    "technical-evaluation",
    "standard",
    "dataset",
    "interpretive-text",
    "stakeholder-account",
    "critical-analysis",
    "private-report",
]
IntentNoveltyStandard = Literal[
    "bounded-comparative",
    "incremental",
    "theoretical",
    "methodological",
    "contextual",
    "critical",
    "interpretive",
    "not-claimed",
]
IntentAutonomyLevel = Literal["human-only", "suggest", "prepare-reversible", "execute-reversible"]
IntentStoppingCondition = Literal[
    "source-exhaustion",
    "coverage-threshold",
    "interpretive-saturation",
    "benchmark-complete",
    "nearest-prior-work-challenged",
    "protocol-complete",
    "resource-budget",
    "researcher-decision",
]
IntentChangeCategory = Literal["primary-use-case", "corpus-scope", "novelty-scope"]
IntentRevisionStatus = Literal["draft", "accepted"]
IntentPolicySubject = Literal["human", "model", "system"]
IntentHumanGate = Literal[
    "intent-acceptance",
    "scope-change",
    "external-egress",
    "evidence-adjudication",
    "claim-approval",
    "publication",
]
IntentPolicyAction = Literal[
    "accept-intent",
    "propose-query",
    "recommend-stopping",
    "prepare-screening-batch",
    "prepare-draft-output",
    "execute-approved-query",
    "execute-approved-screening-batch",
    "change-scope",
    "external-egress",
    "adjudicate-evidence",
    "approve-claim",
    "publish-output",
    "confirm-stopping",
]
IntentPolicyOutcome = Literal["allow", "deny", "recommend-human", "require-confirmation"]
IntentOutputLabel = Literal[
    "systematic-working-output",
    "theory-working-output",
    "technical-working-output",
    "hermeneutic-working-output",
    "critical-working-output",
    "novelty-working-output",
    "empirical-working-output",
]


class IntentImpactRequest(ContractModel):
    root: str = Field(min_length=1, max_length=4096)
    expected_revision: int = Field(ge=0, le=9_007_199_254_740_991)
    primary_use_case: IntentPrimaryUseCase
    source_kinds: tuple[IntentSourceKind, ...] = Field(max_length=32)
    language_codes: tuple[str, ...] = Field(max_length=32)
    start_year: int | None = Field(default=None, ge=1000, le=9999)
    end_year: int | None = Field(default=None, ge=1000, le=9999)
    include_private_reports: bool
    novelty_standard: IntentNoveltyStandard | None

    @model_validator(mode="after")
    def validate_scope(self) -> IntentImpactRequest:
        if len(set(self.source_kinds)) != len(self.source_kinds):
            raise ValueError("source kinds must be unique")
        if len(set(self.language_codes)) != len(self.language_codes):
            raise ValueError("language codes must be unique")
        if any(
            not value
            or len(value) > 100
            or value != value.lower()
            or not all(character.isascii() and (character.isalnum() or character in "._-") for character in value)
            for value in self.language_codes
        ):
            raise ValueError("language codes must be canonical lower-case short codes")
        if (self.start_year is None) != (self.end_year is None):
            raise ValueError("temporal scope must provide both bounds or neither")
        if self.start_year is not None and self.end_year is not None and self.start_year > self.end_year:
            raise ValueError("temporal scope must be ordered")
        return self


class IntentDraftRequest(IntentImpactRequest):
    research_objective: str = Field(max_length=4000)
    contribution_intent: str = Field(max_length=4000)
    phenomenon: str = Field(max_length=4000)
    unit_of_analysis: str = Field(max_length=4000)
    level_of_analysis: str = Field(max_length=4000)
    evidence_types: tuple[IntentEvidenceType, ...] = Field(max_length=32)
    novelty_rationale: str = Field(max_length=4000)
    autonomy_level: IntentAutonomyLevel
    stopping_conditions: tuple[IntentStoppingCondition, ...] = Field(min_length=1, max_length=3)
    revision_rationale: str = Field(min_length=1, max_length=4000)
    impact_acknowledgement: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_draft_collections(self) -> IntentDraftRequest:
        if len(set(self.evidence_types)) != len(self.evidence_types):
            raise ValueError("evidence types must be unique")
        if len(set(self.stopping_conditions)) != len(self.stopping_conditions):
            raise ValueError("stopping conditions must be unique")
        for value in (
            self.research_objective,
            self.contribution_intent,
            self.phenomenon,
            self.unit_of_analysis,
            self.level_of_analysis,
            self.novelty_rationale,
            self.revision_rationale,
        ):
            if any(ord(character) < 32 and character not in "\n\r\t" for character in value):
                raise ValueError("intent narrative contains unsupported control characters")
        return self

    def to_impact_request(self) -> IntentImpactRequest:
        return IntentImpactRequest(
            root=self.root,
            expected_revision=self.expected_revision,
            primary_use_case=self.primary_use_case,
            source_kinds=self.source_kinds,
            language_codes=self.language_codes,
            start_year=self.start_year,
            end_year=self.end_year,
            include_private_reports=self.include_private_reports,
            novelty_standard=self.novelty_standard,
        )


class IntentAcceptRequest(ContractModel):
    root: str = Field(min_length=1, max_length=4096)
    expected_revision: int = Field(ge=1, le=9_007_199_254_740_991)
    expected_revision_content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    confirmed: bool
    decision_rationale: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def validate_rationale(self) -> IntentAcceptRequest:
        if any(ord(character) < 32 and character not in "\n\r\t" for character in self.decision_rationale):
            raise ValueError("intent acceptance rationale contains unsupported control characters")
        return self


class IntentPolicyRequest(ContractModel):
    root: str = Field(min_length=1, max_length=4096)
    action: IntentPolicyAction
    subject_type: IntentPolicySubject
    stopping_condition: IntentStoppingCondition | None = None


class IntentGoverningReference(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    document_type: Literal["research-observatory-research-intent-reference"] = (
        "research-observatory-research-intent-reference"
    )
    contract_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    intent_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    revision_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    revision: int = Field(ge=1, le=9_007_199_254_740_991)
    revision_content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class IntentPolicyDecision(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    decision_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    evaluated_at: str
    action: IntentPolicyAction
    subject_type: IntentPolicySubject
    outcome: IntentPolicyOutcome
    reason_code: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=100)
    explanation: str = Field(min_length=1, max_length=1000)
    governing_intent: IntentGoverningReference | None
    required_gates: tuple[IntentHumanGate, ...] = Field(max_length=6)
    output_label: IntentOutputLabel | None
    stopping_requires_human_confirmation: bool


class IntentImpactPreview(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    expected_revision: int = Field(ge=0, le=9_007_199_254_740_991)
    change_categories: tuple[IntentChangeCategory, ...] = Field(max_length=3)
    affected_workflows: tuple[str, ...] = Field(max_length=32)
    affected_outputs: tuple[str, ...] = Field(max_length=32)
    warnings: tuple[str, ...] = Field(max_length=8)
    acknowledgement_required: bool
    acknowledgement_token: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_acknowledgement(self) -> IntentImpactPreview:
        if self.acknowledgement_required != (self.acknowledgement_token is not None):
            raise ValueError("impact acknowledgement state is inconsistent")
        return self


class IntentDraftProjection(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    intent_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    revision_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    revision: int = Field(ge=1, le=9_007_199_254_740_991)
    revision_content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    created_at: str
    status: IntentRevisionStatus = "draft"
    primary_use_case: IntentPrimaryUseCase
    epistemic_mode: IntentEpistemicMode
    research_objective: str = Field(max_length=4000)
    contribution_intent: str = Field(max_length=4000)
    phenomenon: str = Field(max_length=4000)
    unit_of_analysis: str = Field(max_length=4000)
    level_of_analysis: str = Field(max_length=4000)
    source_kinds: tuple[IntentSourceKind, ...] = Field(max_length=32)
    language_codes: tuple[str, ...] = Field(max_length=32)
    start_year: int | None = Field(default=None, ge=1000, le=9999)
    end_year: int | None = Field(default=None, ge=1000, le=9999)
    include_private_reports: bool
    evidence_types: tuple[IntentEvidenceType, ...] = Field(max_length=32)
    novelty_standard: IntentNoveltyStandard | None
    novelty_rationale: str = Field(max_length=4000)
    autonomy_level: IntentAutonomyLevel
    stopping_conditions: tuple[IntentStoppingCondition, ...] = Field(min_length=1, max_length=3)
    revision_rationale: str = Field(min_length=1, max_length=4000)
    unresolved_decisions: tuple[str, ...] = Field(max_length=64)
    decision_complete: bool
    can_request_acceptance: bool
    launch_ready: bool = False

    @model_validator(mode="after")
    def validate_decision_state(self) -> IntentDraftProjection:
        if self.decision_complete != (not self.unresolved_decisions):
            raise ValueError("intent decision-completeness projection is inconsistent")
        if self.status == "draft":
            if self.can_request_acceptance != self.decision_complete or self.launch_ready:
                raise ValueError("only decision-complete drafts may request acceptance")
        elif not self.decision_complete or self.can_request_acceptance or not self.launch_ready:
            raise ValueError("accepted intent projection is inconsistent")
        return self


class IntentRevisionSummary(ContractModel):
    revision: int = Field(ge=1, le=9_007_199_254_740_991)
    revision_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    revision_content_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    created_at: str
    status: IntentRevisionStatus = "draft"
    primary_use_case: IntentPrimaryUseCase
    unresolved_decision_count: int = Field(ge=0, le=64)


class IntentWorkspaceProjection(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    project_id: str = Field(pattern=(r"^[0-9a-f]{8}-[0-9a-f]{4}-[47][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"))
    current: IntentDraftProjection | None
    history: tuple[IntentRevisionSummary, ...] = Field(max_length=100)


class DeletionDisclosure(ContractModel):
    disclosure_version: Literal["secure-deletion-disclosure-v1"]
    scope: Literal["project-cache-only"]
    logical_removal: Literal[True]
    physical_erasure_guaranteed: Literal[False]
    canonical_project_data_excluded: Literal[True]
    limitations: tuple[str, ...] = Field(min_length=4, max_length=8)


class ProjectPrivacyRequest(ProjectRootRequest):
    pass


class PrivacyPolicyUpdateRequest(ProjectRootRequest):
    expected_revision: int = Field(ge=0, le=9_007_199_254_740_991)
    network_policy: PrivacyNetworkPolicy
    remote_model_approval: RemoteModelApproval
    telemetry_mode: TelemetryMode
    log_retention_days: int = Field(ge=1, le=90)
    document_retention: DocumentRetentionPolicy
    cache_retention_days: int = Field(ge=1, le=90)
    egress_consent_token: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def validate_egress_consent(self) -> PrivacyPolicyUpdateRequest:
        expected = "acknowledge-egress-preview-v1"
        if self.network_policy is PrivacyNetworkPolicy.OFFLINE:
            if self.egress_consent_token is not None:
                raise ValueError("offline policy cannot record an egress consent token")
        elif self.egress_consent_token != expected:
            raise ValueError("non-offline policy requires the exact informed-consent token")
        return self


class PrivacyPolicyProjection(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    project_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    revision: int = Field(ge=0, le=9_007_199_254_740_991)
    defaults_applied: bool
    network_policy: PrivacyNetworkPolicy
    remote_model_approval: RemoteModelApproval
    telemetry_mode: TelemetryMode
    log_retention_days: int = Field(ge=1, le=90)
    document_retention: DocumentRetentionPolicy
    cache_retention_days: int = Field(ge=1, le=90)
    egress_consent_recorded: bool
    egress_enforcement: EgressEnforcement
    deletion_disclosure: DeletionDisclosure

    @model_validator(mode="after")
    def validate_policy_state(self) -> PrivacyPolicyProjection:
        if self.defaults_applied != (self.revision == 0):
            raise ValueError("privacy defaults state must match revision")
        if self.egress_consent_recorded != (self.network_policy is not PrivacyNetworkPolicy.OFFLINE):
            raise ValueError("egress consent state must match network policy")
        expected = (
            EgressEnforcement.REQUIRE_TASK_PREVIEW
            if self.network_policy is PrivacyNetworkPolicy.APPROVED_PROVIDERS
            else EgressEnforcement.DENY
        )
        if self.egress_enforcement is not expected:
            raise ValueError("egress enforcement must match network policy")
        return self


class CacheClearPreviewRequest(ProjectRootRequest):
    pass


class CacheClearPreview(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    project_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    policy_revision: int = Field(ge=0, le=9_007_199_254_740_991)
    preview_token: str = Field(pattern=r"^[0-9a-f]{32}$")
    confirmation: str = Field(pattern=r"^clear-cache:[0-9a-f]{32}$")
    expires_at: datetime
    item_count: int = Field(ge=0, le=100_000)
    byte_count: int = Field(ge=0, le=9_007_199_254_740_991)
    deletion_disclosure: DeletionDisclosure


class CacheClearRequest(ProjectRootRequest):
    preview_token: str = Field(pattern=r"^[0-9a-f]{32}$")
    confirmation: str = Field(pattern=r"^clear-cache:[0-9a-f]{32}$")

    @model_validator(mode="after")
    def validate_confirmation(self) -> CacheClearRequest:
        if self.confirmation != f"clear-cache:{self.preview_token}":
            raise ValueError("cache confirmation must match the preview token")
        return self


class CacheClearResult(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    project_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
    state: CacheClearState
    item_count: int = Field(ge=0, le=100_000)
    byte_count: int = Field(ge=0, le=9_007_199_254_740_991)
    cleanup_pending: bool
    deletion_disclosure: DeletionDisclosure

    @model_validator(mode="after")
    def validate_cleanup_state(self) -> CacheClearResult:
        if self.cleanup_pending != (self.state is CacheClearState.CLEARED_CLEANUP_PENDING):
            raise ValueError("cache cleanup state must match cleanup_pending")
        return self


class OperationState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OperationStatus(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    operation_id: str = Field(pattern=r"^op-[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
    kind: str = Field(pattern=r"^[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*)*$")
    state: OperationState
    sequence: int = Field(ge=0)
    progress_percent: int = Field(ge=0, le=100)
    cancellation_requested: bool
    created_at: datetime
    updated_at: datetime
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")


class OperationPage(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    items: tuple[OperationStatus, ...]
    next_cursor: str | None = None


class OperationProgressEvent(ContractModel):
    schema_version: str = CORE_API_SCHEMA_VERSION
    operation_id: str = Field(pattern=r"^op-[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
    sequence: int = Field(ge=1)
    state: OperationState
    progress_percent: int = Field(ge=0, le=100)
    terminal: bool
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
