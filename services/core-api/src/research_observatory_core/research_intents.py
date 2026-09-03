"""Versioned Research Intent draft, impact-preview, and persistence authority."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from threading import RLock
from typing import Any, Literal, Protocol, cast

from .domain_contracts import is_uuid_v7, new_uuid_v7
from .logging import emit_log_record
from .models import (
    IntentAcceptRequest,
    IntentDraftProjection,
    IntentDraftRequest,
    IntentGoverningReference,
    IntentImpactPreview,
    IntentImpactRequest,
    IntentPolicyDecision,
    IntentPolicyRequest,
    IntentRevisionSummary,
    IntentWorkspaceProjection,
    WorkflowProfileCatalogProjection,
    WorkflowProfileProjection,
    WorkflowProfileStageProjection,
)
from .ports.repositories import (
    DependencyStaleState,
    IntentAuditEvent,
    IntentPolicyAuditEvent,
    IntentPolicyDecisionRecord,
    IntentRevisionRecord,
    IntentRevisionRepository,
    RepositoryConflict,
    RepositoryIdempotencyConflict,
    RepositoryProblem,
    WorkflowAuthorityMutation,
    WorkflowAuthorityRecord,
    WorkflowAuthorityWitness,
)
from .projects import ProjectLifecycleProblem, ProjectLifecycleService
from .research_intent_contracts import (
    decode_research_intent_revision,
    governing_research_intent_reference,
    research_intent_snapshot_json,
)
from .workflow_profile_contracts import (
    APPROVED_WORKFLOW_PROFILE_CATALOG_SHA256,
    approved_workflow_profile_catalog,
    decode_project_workflow_selection,
    decode_workflow_profile_migration,
)

_RepositoryFactory = Callable[[Path, str], IntentRevisionRepository]


class _StaleStateRepository(Protocol):
    def stale_states(self, *, output_revision_id: str | None = None) -> tuple[DependencyStaleState, ...]: ...


_StaleStateRepositoryFactory = Callable[[Path, str], _StaleStateRepository]
_MAX_HISTORY = 100


class _UnavailableIntentRepository(IntentRevisionRepository):
    """Fail-closed composition used when no concrete local adapter is supplied."""

    def read(self) -> tuple[IntentRevisionRecord, ...]:
        raise RepositoryProblem("research intent repository is unavailable")

    def read_workflow_authority(self) -> WorkflowAuthorityMutation:
        raise RepositoryProblem("workflow profile repository is unavailable")

    def replay(
        self,
        *,
        manifest_project_id: str,
        actor_id: str,
        idempotency_key: str,
        command_sha256: str,
        event_type: str = "intent.draft.saved",
    ) -> IntentRevisionRecord | None:
        del manifest_project_id, actor_id, idempotency_key, command_sha256, event_type
        raise RepositoryProblem("research intent repository is unavailable")

    def append_policy_decision(
        self,
        *,
        record: IntentPolicyDecisionRecord,
        event: IntentPolicyAuditEvent,
    ) -> None:
        del record, event
        raise RepositoryProblem("research intent repository is unavailable")

    def append(
        self,
        *,
        expected_revision: int,
        domain_project_id: str,
        manifest_project_id: str,
        record: IntentRevisionRecord,
        event: IntentAuditEvent,
        workflow_authority: WorkflowAuthorityMutation | None = None,
    ) -> IntentRevisionRecord:
        del expected_revision, domain_project_id, manifest_project_id, record, event, workflow_authority
        raise RepositoryProblem("research intent repository is unavailable")


class _UnavailableStaleStateRepository:
    def stale_states(self, *, output_revision_id: str | None = None) -> tuple[DependencyStaleState, ...]:
        del output_revision_id
        raise RepositoryProblem("dependency stale-state repository is unavailable")


_USE_CASE_MODE = {
    "rapid-orientation": "systematic",
    "systematic-review": "systematic",
    "living-review": "systematic",
    "theory-synthesis": "theory",
    "hermeneutic-inquiry": "hermeneutic",
    "critical-problematization": "critical",
    "technical-landscape": "technical",
    "novelty-audit": "novelty",
    "empirical-study-design": "empirical",
    "empirical-study-to-article": "empirical",
    "empirical-results-to-article": "empirical",
    "theory-article-development": "theory",
    "critical-article-development": "critical",
    "manuscript-review-revision": "empirical",
}
_WORKFLOW_CATALOG = approved_workflow_profile_catalog()
_PROFILE_BY_ID = {
    cast(str, profile["profileId"]): profile
    for profile in cast(Sequence[Mapping[str, object]], _WORKFLOW_CATALOG["profiles"])
}

_INTENT_GUIDANCE_BY_PROFILE: Mapping[str, Mapping[str, object]] = {
    "rapid-orientation": {
        "example": "Map the main approaches and unresolved questions in a new field.",
        "evidenceTypes": ("empirical-study", "systematic-review"),
        "noveltyStandard": "not-claimed",
        "autonomyLevel": "suggest",
        "stoppingConditions": ("coverage-threshold",),
        "warning": "Rapid orientation supports bounded understanding; it does not claim exhaustive coverage.",
    },
    "systematic-review": {
        "example": "Estimate and explain an intervention effect from eligible studies.",
        "evidenceTypes": ("empirical-study", "systematic-review"),
        "noveltyStandard": "bounded-comparative",
        "autonomyLevel": "suggest",
        "stoppingConditions": ("coverage-threshold",),
        "warning": "Coverage claims remain bounded by the recorded protocol, sources, dates, and languages.",
    },
    "living-review": {
        "example": "Maintain an evidence synthesis as qualifying studies appear.",
        "evidenceTypes": ("empirical-study", "systematic-review"),
        "noveltyStandard": "incremental",
        "autonomyLevel": "suggest",
        "stoppingConditions": ("coverage-threshold",),
        "warning": "Every update preserves its search boundary and prior synthesis revision.",
    },
    "theory-synthesis": {
        "example": "Reconcile competing mechanisms into a bounded conceptual model.",
        "evidenceTypes": ("theoretical-work", "empirical-study"),
        "noveltyStandard": "theoretical",
        "autonomyLevel": "suggest",
        "stoppingConditions": ("interpretive-saturation",),
        "warning": "Conceptual integration must preserve disagreements and evidentiary limits.",
    },
    "hermeneutic-inquiry": {
        "example": "Develop a situated interpretation across a bounded textual corpus.",
        "evidenceTypes": ("interpretive-text",),
        "noveltyStandard": "interpretive",
        "autonomyLevel": "suggest",
        "stoppingConditions": ("interpretive-saturation", "researcher-decision"),
        "warning": "Interpretations remain researcher-authored and tied to the recorded corpus and frame.",
    },
    "critical-problematization": {
        "example": "Surface exclusions and consequences within a dominant framing.",
        "evidenceTypes": ("critical-analysis", "stakeholder-account"),
        "noveltyStandard": "critical",
        "autonomyLevel": "suggest",
        "stoppingConditions": ("interpretive-saturation", "researcher-decision"),
        "warning": "The workflow must preserve standpoint, counter-evidence, and affected voices.",
    },
    "technical-landscape": {
        "example": "Compare architectures and evaluated capabilities for a technical domain.",
        "evidenceTypes": ("technical-evaluation", "standard", "dataset"),
        "noveltyStandard": "bounded-comparative",
        "autonomyLevel": "suggest",
        "stoppingConditions": ("benchmark-complete",),
        "warning": "Comparisons are limited to compatible evidence, versions, and benchmark conditions.",
    },
    "novelty-audit": {
        "example": "Challenge a proposed contribution against the closest documented alternatives.",
        "evidenceTypes": ("empirical-study", "theoretical-work", "technical-evaluation"),
        "noveltyStandard": "bounded-comparative",
        "autonomyLevel": "suggest",
        "stoppingConditions": ("nearest-prior-work-challenged",),
        "warning": (
            "A novelty claim is provisional until nearest prior work and plausible counterexamples are challenged."
        ),
    },
    "empirical-study-design": {
        "example": "Design a study without inventing participants, results, or feasibility evidence.",
        "evidenceTypes": ("empirical-study", "systematic-review"),
        "noveltyStandard": "methodological",
        "autonomyLevel": "suggest",
        "stoppingConditions": ("protocol-complete",),
        "warning": "The researcher retains authority over ethics, recruitment, conduct, and interpretation.",
    },
    "empirical-study-to-article": {
        "example": "Develop a manuscript from a documented study and analysis plan.",
        "evidenceTypes": ("empirical-study", "dataset"),
        "noveltyStandard": "contextual",
        "autonomyLevel": "suggest",
        "stoppingConditions": ("protocol-complete", "researcher-decision"),
        "warning": "Unreported or missing results remain unreported or missing.",
    },
    "empirical-results-to-article": {
        "example": "Develop an article from completed, traceable empirical results.",
        "evidenceTypes": ("empirical-study", "dataset"),
        "noveltyStandard": "incremental",
        "autonomyLevel": "suggest",
        "stoppingConditions": ("researcher-decision",),
        "warning": "No result, statistic, or participant detail may be inferred when absent.",
    },
    "theory-article-development": {
        "example": "Develop a theory article from traceable concepts and propositions.",
        "evidenceTypes": ("theoretical-work", "empirical-study"),
        "noveltyStandard": "theoretical",
        "autonomyLevel": "suggest",
        "stoppingConditions": ("interpretive-saturation", "researcher-decision"),
        "warning": "The system can prepare arguments; the researcher owns interpretation and claims.",
    },
    "critical-article-development": {
        "example": "Develop a critical article with explicit standpoint and counter-evidence.",
        "evidenceTypes": ("critical-analysis", "stakeholder-account", "interpretive-text"),
        "noveltyStandard": "critical",
        "autonomyLevel": "suggest",
        "stoppingConditions": ("interpretive-saturation", "researcher-decision"),
        "warning": "The article must not erase contested positions or affected perspectives.",
    },
    "manuscript-review-revision": {
        "example": "Address reviewer comments without silently broadening claims.",
        "evidenceTypes": ("empirical-study", "theoretical-work", "technical-evaluation"),
        "noveltyStandard": "not-claimed",
        "autonomyLevel": "suggest",
        "stoppingConditions": ("researcher-decision",),
        "warning": "Reviewer responses and claim changes remain explicit, traceable researcher decisions.",
    },
}
if set(_INTENT_GUIDANCE_BY_PROFILE) != set(_PROFILE_BY_ID):
    raise RuntimeError("workflow profile intent guidance does not match the governed catalog")
INTENT_PROFILE_GUIDANCE_VERSION: Literal["1.0.0"] = "1.0.0"
_INTENT_PROFILE_GUIDANCE_DOCUMENT: Mapping[str, object] = {
    "schemaVersion": "1.0",
    "documentType": "research-observatory-intent-profile-guidance",
    "guidanceVersion": INTENT_PROFILE_GUIDANCE_VERSION,
    "profileCatalogHash": APPROVED_WORKFLOW_PROFILE_CATALOG_SHA256,
    "profiles": _INTENT_GUIDANCE_BY_PROFILE,
}


def intent_profile_guidance_sha256(value: object) -> str:
    """Hash the exact canonical guidance bytes exposed across the Core boundary."""

    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    )


APPROVED_INTENT_PROFILE_GUIDANCE_SHA256 = "sha256:2feffbaf216da3adb4d8fe0b3ca6e2579cdc2dcedc2d57341086a14def5fe0d2"
if intent_profile_guidance_sha256(_INTENT_PROFILE_GUIDANCE_DOCUMENT) != APPROVED_INTENT_PROFILE_GUIDANCE_SHA256:
    raise RuntimeError("intent profile guidance differs from its approved content hash")


def approved_intent_profile_guidance() -> Mapping[str, object]:
    """Return detached exact guidance bytes for contract and substitution checks."""

    return cast(Mapping[str, object], json.loads(json.dumps(_INTENT_PROFILE_GUIDANCE_DOCUMENT)))


def _stage_label(page_contract_id: str) -> str:
    if page_contract_id == "intent-contract.html":
        return "Research Intent"
    return page_contract_id.removesuffix(".html").replace("-", " ").title().replace(" And ", " & ")


def _profile_reference(profile_id: str) -> dict[str, object]:
    profile = _PROFILE_BY_ID[profile_id]
    governed = cast(Mapping[str, object], _WORKFLOW_CATALOG["governedReference"])
    return {
        "referenceId": governed["referenceId"],
        "referenceVersion": governed["referenceVersion"],
        "workflowCatalogHash": governed["workflowCatalogHash"],
        "pageContractsHash": governed["pageContractsHash"],
        "profileCatalogVersion": _WORKFLOW_CATALOG["profileCatalogVersion"],
        "profileCatalogHash": APPROVED_WORKFLOW_PROFILE_CATALOG_SHA256,
        "profileId": profile["profileId"],
        "profileVersion": profile["profileVersion"],
        "profileRevision": profile["profileRevision"],
        "sourceWorkflowHash": profile["sourceWorkflowHash"],
    }


def _workflow_catalog_projection() -> WorkflowProfileCatalogProjection:
    governed = cast(Mapping[str, object], _WORKFLOW_CATALOG["governedReference"])
    profiles: list[WorkflowProfileProjection] = []
    for profile in cast(Sequence[Mapping[str, object]], _WORKFLOW_CATALOG["profiles"]):
        guidance = _INTENT_GUIDANCE_BY_PROFILE[cast(str, profile["profileId"])]
        stages = tuple(
            WorkflowProfileStageProjection(
                stage_key=cast(str, stage["stageKey"]),
                order=cast(int, stage["order"]),
                page_contract_id=cast(str, stage["pageContractId"]),
                label=_stage_label(cast(str, stage["pageContractId"])),
                optional=cast(bool, stage["optional"]),
                rationale=cast(str, stage["rationale"]),
                checkpoint_state=cast(Any, cast(Mapping[str, object], stage["checkpoint"])["state"]),
                checkpoint_rationale=cast(str, cast(Mapping[str, object], stage["checkpoint"])["rationale"]),
            )
            for stage in cast(Sequence[Mapping[str, object]], profile["stages"])
        )
        profiles.append(
            WorkflowProfileProjection(
                profile_id=cast(Any, profile["profileId"]),
                epistemic_mode=cast(Any, _USE_CASE_MODE[cast(str, profile["profileId"])]),
                title=cast(str, profile["title"]),
                purpose=cast(str, profile["purpose"]),
                example=cast(str, guidance["example"]),
                expected_outputs=tuple(cast(Sequence[str], profile["expectedOutputs"])),
                process_form=cast(Any, profile["cyclePolicy"]),
                default_evidence_types=tuple(cast(Sequence[Any], guidance["evidenceTypes"])),
                default_novelty_standard=cast(Any, guidance["noveltyStandard"]),
                default_autonomy_level=cast(Any, guidance["autonomyLevel"]),
                default_stopping_conditions=tuple(cast(Sequence[Any], guidance["stoppingConditions"])),
                warning=cast(str, guidance["warning"]),
                stages=stages,
            )
        )
    return WorkflowProfileCatalogProjection(
        reference_id=cast(Any, governed["referenceId"]),
        reference_version=cast(Any, governed["referenceVersion"]),
        profile_catalog_version=cast(Any, _WORKFLOW_CATALOG["profileCatalogVersion"]),
        profile_catalog_hash=APPROVED_WORKFLOW_PROFILE_CATALOG_SHA256,
        intent_guidance_version=INTENT_PROFILE_GUIDANCE_VERSION,
        intent_guidance_hash=APPROVED_INTENT_PROFILE_GUIDANCE_SHA256,
        registered_tool_page_contract_ids=tuple(
            cast(Sequence[str], _WORKFLOW_CATALOG["registeredToolPageContractIds"])
        ),
        profiles=tuple(profiles),
    )


_GATE_ACTIONS = {
    "accept-intent": "intent-acceptance",
    "change-scope": "scope-change",
    "external-egress": "external-egress",
    "adjudicate-evidence": "evidence-adjudication",
    "approve-claim": "claim-approval",
    "publish-output": "publication",
}
_OUTPUT_LABELS = {
    "systematic": "systematic-working-output",
    "theory": "theory-working-output",
    "technical": "technical-working-output",
    "hermeneutic": "hermeneutic-working-output",
    "critical": "critical-working-output",
    "novelty": "novelty-working-output",
    "empirical": "empirical-working-output",
}


@dataclass(slots=True)
class IntentProblem(Exception):
    status: int
    code: str
    title: str
    detail: str
    remediation: str
    retryable: bool = False

    def __str__(self) -> str:
        return self.code


def _problem(
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    remediation: str,
    retryable: bool = False,
) -> IntentProblem:
    return IntentProblem(status, code, title, detail, remediation, retryable)


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _command_sha256(command: IntentDraftRequest, *, manifest_project_id: str, actor_id: str) -> str:
    payload = {
        "actor": {"actorId": actor_id, "actorType": "human"},
        "command": command.model_dump(mode="json", by_alias=True),
        "manifestProjectId": manifest_project_id,
        "operation": "intent.draft.save",
        "schemaVersion": "1.0",
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _accept_command_sha256(command: IntentAcceptRequest, *, manifest_project_id: str, actor_id: str) -> str:
    payload = {
        "actor": {"actorId": actor_id, "actorType": "human"},
        "command": command.model_dump(mode="json", by_alias=True),
        "manifestProjectId": manifest_project_id,
        "operation": "intent.accept",
        "schemaVersion": "1.0",
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _statement(value: str) -> dict[str, str]:
    clean = value.strip()
    return (
        {"state": "specified", "value": clean}
        if clean
        else {"state": "unknown", "rationale": "Not yet specified in this draft."}
    )


def _specified_value(value: object) -> str:
    if isinstance(value, Mapping) and value.get("state") == "specified" and isinstance(value.get("value"), str):
        return cast(str, value["value"])
    return ""


def _mode_requirements(use_case: str, mode: str) -> dict[str, object]:
    if mode == "systematic":
        protocol = (
            "living-review"
            if use_case == "living-review"
            else ("scoping-review" if use_case == "rapid-orientation" else "systematic-review")
        )
        return {
            "kind": mode,
            "protocol": protocol,
            "inclusionLogic": "Researcher-defined criteria retained with every inclusion and exclusion decision.",
            "comprehensivenessTarget": "bounded" if use_case == "rapid-orientation" else "exhaustive",
        }
    if mode == "theory":
        return {"kind": mode, "synthesisApproach": "integrative", "theoreticalLenses": ["Researcher-declared lens"]}
    if mode == "technical":
        return {
            "kind": mode,
            "evaluationTargets": ["Researcher-declared technical target"],
            "benchmarkDimensions": ["validity"],
        }
    if mode == "hermeneutic":
        return {
            "kind": mode,
            "interpretiveTradition": "Researcher-declared interpretive tradition",
            "iterationLogic": "Iterate among search, reading, memoing, and reframing with retained history.",
        }
    if mode == "critical":
        return {
            "kind": mode,
            "criticalTradition": "Researcher-declared critical tradition",
            "affectedStakeholders": ["Stakeholders identified by the researcher"],
            "reflexivityCommitment": "Retain assumptions, standpoint, alternatives, and researcher adjudication.",
        }
    if mode == "novelty":
        return {"kind": mode, "opportunityTypes": ["evidence-gap"], "nearestPriorWorkChallenge": True}
    return {"kind": "empirical", "studyType": "observational", "designConstraints": []}


def _autonomy(level: str) -> dict[str, object]:
    actions = {
        "human-only": [],
        "suggest": ["propose-query", "recommend-stopping"],
        "prepare-reversible": [
            "propose-query",
            "recommend-stopping",
            "prepare-screening-batch",
            "prepare-draft-output",
        ],
        "execute-reversible": [
            "propose-query",
            "recommend-stopping",
            "prepare-screening-batch",
            "prepare-draft-output",
            "execute-approved-query",
            "execute-approved-screening-batch",
        ],
    }[level]
    return {
        "level": level,
        "allowedActions": actions,
        "requiredHumanGates": [
            "intent-acceptance",
            "scope-change",
            "evidence-adjudication",
            "claim-approval",
            "publication",
        ],
        "mayAcceptIntent": False,
        "mayChangeScope": False,
    }


def _unresolved(command: IntentDraftRequest) -> list[str]:
    unresolved: list[str] = []
    for value, code in (
        (command.research_objective, "research-question"),
        (command.contribution_intent, "contribution-intent"),
        (command.phenomenon, "phenomenon"),
        (command.unit_of_analysis, "unit-of-analysis"),
        (command.level_of_analysis, "level-of-analysis"),
    ):
        if not value.strip():
            unresolved.append(code)
    if not command.source_kinds or not command.language_codes or command.start_year is None or command.end_year is None:
        unresolved.append("source-scope")
    if not command.evidence_types:
        unresolved.append("evidence-types")
    if command.novelty_standard is None or not command.novelty_rationale.strip():
        unresolved.append("novelty-standard")
    return unresolved


def _source_scope(command: IntentDraftRequest) -> dict[str, object]:
    if (
        not command.source_kinds
        and not command.language_codes
        and command.start_year is None
        and command.end_year is None
    ):
        return {"state": "unknown", "rationale": "Source and corpus boundaries are not yet specified."}
    if not command.source_kinds or not command.language_codes or command.start_year is None or command.end_year is None:
        raise _problem(
            status=422,
            code="RO-CORE-INTENT-SCOPE-INCOMPLETE",
            title="Corpus scope is only partially specified",
            detail="A structured corpus scope requires source kinds, languages, and both temporal bounds.",
            remediation="Complete every corpus-scope field or clear the group and save it as unresolved.",
        )
    return {
        "state": "specified",
        "sourceKinds": list(command.source_kinds),
        "languages": list(command.language_codes),
        "temporalCoverage": {"kind": "bounded", "startYear": command.start_year, "endYear": command.end_year},
        "privateReports": "allowed" if command.include_private_reports else "excluded",
        "rationale": "Researcher-authored corpus boundary for this intent revision.",
    }


def _novelty(command: IntentDraftRequest) -> dict[str, object]:
    if command.novelty_standard is None and not command.novelty_rationale.strip():
        return {"state": "unknown", "rationale": "Novelty standard is not yet specified."}
    if command.novelty_standard is None or not command.novelty_rationale.strip():
        raise _problem(
            status=422,
            code="RO-CORE-INTENT-NOVELTY-INCOMPLETE",
            title="Novelty scope is only partially specified",
            detail="A selected novelty standard requires the researcher's bounded rationale.",
            remediation="Add the rationale or clear the novelty selection and save it as unresolved.",
        )
    return {"state": "specified", "standard": command.novelty_standard, "rationale": command.novelty_rationale.strip()}


def _content_hash(revision: Mapping[str, object]) -> str:
    without_hash = {key: value for key, value in revision.items() if key != "revisionContentHash"}
    return "sha256:" + hashlib.sha256(_canonical_json(without_hash).encode("utf-8")).hexdigest()


def _authority_content_hash(value: Mapping[str, object], field: str) -> str:
    without_hash = {key: item for key, item in value.items() if key != field}
    return "sha256:" + hashlib.sha256(_canonical_json(without_hash).encode("utf-8")).hexdigest()


def _intent_reference(revision: Mapping[str, object]) -> dict[str, object]:
    return {
        "schemaVersion": "1.0",
        "documentType": "research-observatory-research-intent-reference",
        "contractVersion": revision["contractVersion"],
        "intentId": revision["intentId"],
        "revisionId": revision["revisionId"],
        "revision": revision["revision"],
        "revisionContentHash": revision["revisionContentHash"],
    }


def _initial_workflow_selection(
    intent: Mapping[str, object],
    *,
    actor_id: str,
    selected_at: str,
) -> dict[str, object]:
    selection: dict[str, object] = {
        "schemaVersion": "1.0",
        "documentType": "research-observatory-project-workflow-selection",
        "contractVersion": "1.0.0",
        "selectionId": new_uuid_v7(),
        "selectionRevisionId": new_uuid_v7(),
        "projectId": intent["projectId"],
        "revision": 1,
        "revisionContentHash": "sha256:" + "0" * 64,
        "createdAt": selected_at,
        "selectedBy": {"actorType": "human", "actorId": actor_id},
        "researchIntent": _intent_reference(intent),
        "profile": _profile_reference(cast(str, intent["primaryUseCase"])),
        "parentSelection": None,
        "impactPreview": None,
        "acceptedMigration": None,
    }
    selection["revisionContentHash"] = _authority_content_hash(selection, "revisionContentHash")
    if decode_project_workflow_selection(_WORKFLOW_CATALOG, selection) is None:
        raise RepositoryProblem("initial workflow selection contract is invalid")
    return selection


def _parent_selection(selection: Mapping[str, object]) -> dict[str, object]:
    return {
        "selectionId": selection["selectionId"],
        "selectionRevisionId": selection["selectionRevisionId"],
        "revision": selection["revision"],
        "revisionContentHash": selection["revisionContentHash"],
        "researchIntent": selection["researchIntent"],
        "profile": selection["profile"],
    }


def _migration_stage_mappings(from_profile_id: str, to_profile_id: str) -> list[dict[str, object]]:
    source = cast(Sequence[Mapping[str, object]], _PROFILE_BY_ID[from_profile_id]["stages"])
    target = cast(Sequence[Mapping[str, object]], _PROFILE_BY_ID[to_profile_id]["stages"])
    target_by_key = {cast(str, stage["stageKey"]): stage for stage in target}
    target_by_page = {cast(str, stage["pageContractId"]): stage for stage in target}
    mappings: list[dict[str, object]] = []
    for stage in source:
        stage_key = cast(str, stage["stageKey"])
        page_contract_id = cast(str, stage["pageContractId"])
        exact = target_by_key.get(stage_key)
        equivalent = target_by_page.get(page_contract_id)
        if exact is not None and exact["pageContractId"] == page_contract_id:
            disposition = "retain"
            target_stage_key: str | None = stage_key
            rationale = "The governed target profile retains the same stage and immutable prior history."
        elif equivalent is not None:
            disposition = "map"
            target_stage_key = cast(str, equivalent["stageKey"])
            rationale = "The governed target profile uses a different stage key for the same page contract."
        else:
            disposition = "requires-review"
            target_stage_key = None
            rationale = "The target profile has no equivalent governed stage; retain history and require review."
        mappings.append(
            {
                "fromStageKey": stage_key,
                "disposition": disposition,
                "targetStageKey": target_stage_key,
                "rationale": rationale,
            }
        )
    return mappings


def _changed_workflow_authority(
    parent: Mapping[str, object],
    prior_intent_revision: Mapping[str, object],
    target_intent: Mapping[str, object],
    *,
    actor_id: str,
    selected_at: str,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    parent_reference = _parent_selection(parent)
    prior_intent = _intent_reference(prior_intent_revision)
    from_profile = cast(Mapping[str, object], parent["profile"])
    to_profile = _profile_reference(cast(str, target_intent["primaryUseCase"]))
    decision: dict[str, object] = {
        "decisionId": new_uuid_v7(),
        "decisionContentHash": "sha256:" + "0" * 64,
        "decision": "accepted",
        "decidedAt": selected_at,
        "decidedBy": {"actorType": "human", "actorId": actor_id},
    }
    decision["decisionContentHash"] = _authority_content_hash(decision, "decisionContentHash")
    migration: dict[str, object] = {
        "schemaVersion": "1.0",
        "documentType": "research-observatory-workflow-profile-migration",
        "contractVersion": "1.0.0",
        "migrationId": new_uuid_v7(),
        "migrationContentHash": "sha256:" + "0" * 64,
        "fromProfile": from_profile,
        "toProfile": to_profile,
        "priorResearchIntent": prior_intent,
        "targetResearchIntent": _intent_reference(target_intent),
        "createdAt": selected_at,
        "createdBy": {"actorType": "human", "actorId": actor_id},
        "historyPolicy": "preserve",
        "requiresHumanAcceptance": True,
        "acceptance": decision,
        "stageMappings": _migration_stage_mappings(
            cast(str, from_profile["profileId"]), cast(str, to_profile["profileId"])
        ),
    }
    migration["migrationContentHash"] = _authority_content_hash(migration, "migrationContentHash")
    accepted_migration = {
        "migrationId": migration["migrationId"],
        "migrationContentHash": migration["migrationContentHash"],
        "fromProfile": from_profile,
        "toProfile": to_profile,
        "priorResearchIntent": prior_intent,
        "targetResearchIntent": migration["targetResearchIntent"],
        "acceptance": decision,
    }
    selection: dict[str, object] = {
        "schemaVersion": "1.0",
        "documentType": "research-observatory-project-workflow-selection",
        "contractVersion": "1.0.0",
        "selectionId": parent["selectionId"],
        "selectionRevisionId": new_uuid_v7(),
        "projectId": target_intent["projectId"],
        "revision": cast(int, parent["revision"]) + 1,
        "revisionContentHash": "sha256:" + "0" * 64,
        "createdAt": selected_at,
        "selectedBy": {"actorType": "human", "actorId": actor_id},
        "researchIntent": migration["targetResearchIntent"],
        "profile": to_profile,
        "parentSelection": parent_reference,
        "impactPreview": {
            "priorSelection": parent_reference,
            "targetProfile": to_profile,
            "historyPolicy": "preserve",
            "priorStageStates": [],
            "summary": (
                "Preserve the prior workflow selection and stage history while applying the accepted profile change."
            ),
        },
        "acceptedMigration": accepted_migration,
    }
    selection["revisionContentHash"] = _authority_content_hash(selection, "revisionContentHash")
    if decode_workflow_profile_migration(_WORKFLOW_CATALOG, migration) is None:
        raise RepositoryProblem("workflow profile migration contract is invalid")
    if decode_project_workflow_selection(_WORKFLOW_CATALOG, selection) is None:
        raise RepositoryProblem("changed workflow selection contract is invalid")
    return selection, migration, decision


def _workflow_authority_mutation(
    existing: WorkflowAuthorityMutation,
    *,
    prior_intent: Mapping[str, object] | None,
    target_intent: Mapping[str, object],
    actor_id: str,
) -> WorkflowAuthorityMutation | None:
    selections, _migrations = _validated_workflow_authority(existing)
    selected_at = cast(str, target_intent["createdAt"])
    added_selections: list[WorkflowAuthorityRecord] = []
    added_migrations: list[WorkflowAuthorityRecord] = []
    added_decisions: list[WorkflowAuthorityRecord] = []
    activation: WorkflowAuthorityRecord | None = None
    activation_witness: WorkflowAuthorityWitness | None = None
    parent = selections[-1] if selections else None
    profile_changed = bool(
        prior_intent is not None and prior_intent["primaryUseCase"] != target_intent["primaryUseCase"]
    )
    if parent is None and profile_changed:
        if prior_intent is None:
            raise RepositoryProblem("workflow selection predecessor intent is unavailable")
        parent = _initial_workflow_selection(prior_intent, actor_id=actor_id, selected_at=selected_at)
        added_selections.append(WorkflowAuthorityRecord(revision=1, content_json=_canonical_json(parent)))
    if parent is None:
        initial = _initial_workflow_selection(target_intent, actor_id=actor_id, selected_at=selected_at)
        added_selections.append(WorkflowAuthorityRecord(revision=1, content_json=_canonical_json(initial)))
    elif profile_changed:
        if prior_intent is None:
            raise RepositoryProblem("workflow migration predecessor intent is unavailable")
        changed, migration, decision = _changed_workflow_authority(
            parent,
            prior_intent,
            target_intent,
            actor_id=actor_id,
            selected_at=selected_at,
        )
        revision = cast(int, changed["revision"])
        added_selections.append(WorkflowAuthorityRecord(revision=revision, content_json=_canonical_json(changed)))
        added_migrations.append(WorkflowAuthorityRecord(revision=revision, content_json=_canonical_json(migration)))
        added_decisions.append(WorkflowAuthorityRecord(revision=revision, content_json=_canonical_json(decision)))
    if not added_selections and not added_migrations and not added_decisions:
        return None
    if existing.activation is None and added_selections:
        first_selection = json.loads(added_selections[0].content_json)
        first_intent = cast(Mapping[str, object], first_selection["researchIntent"])
        witness_event_id = new_uuid_v7()
        binding: dict[str, object] = {
            "schemaVersion": "1.1",
            "documentType": "research-observatory-workflow-authority-binding",
            "authority": "ADR-0026",
            "domainProjectId": first_selection["projectId"],
            "activatedAtIntentRevision": first_intent["revision"],
            "firstSelectionRevisionId": first_selection["selectionRevisionId"],
            "firstSelectionContentHash": first_selection["revisionContentHash"],
            "profileCatalogHash": APPROVED_WORKFLOW_PROFILE_CATALOG_SHA256,
            "intentGuidanceVersion": INTENT_PROFILE_GUIDANCE_VERSION,
            "intentGuidanceHash": APPROVED_INTENT_PROFILE_GUIDANCE_SHA256,
            "activationWitnessEventId": witness_event_id,
            "bindingContentHash": "sha256:" + "0" * 64,
        }
        binding["bindingContentHash"] = _authority_content_hash(binding, "bindingContentHash")
        activation_json = _canonical_json(binding)
        activation = WorkflowAuthorityRecord(revision=0, content_json=activation_json)
        activation_witness = WorkflowAuthorityWitness(
            event_id=witness_event_id,
            occurred_at=selected_at,
            actor_id=actor_id,
            record_sha256=hashlib.sha256(activation_json.encode("utf-8")).hexdigest(),
        )
    return WorkflowAuthorityMutation(
        activation=activation,
        activation_witness=activation_witness,
        selections=tuple(added_selections),
        migrations=tuple(added_migrations),
        decisions=tuple(added_decisions),
    )


def _build_revision(
    command: IntentDraftRequest,
    *,
    prior: Mapping[str, object] | None,
    domain_project_id: str,
    actor_id: str,
) -> dict[str, object]:
    revision_number = command.expected_revision + 1
    intent_id = cast(str, prior["intentId"]) if prior is not None else new_uuid_v7()
    mode = _USE_CASE_MODE[command.primary_use_case]
    source_scope = _source_scope(command)
    novelty = _novelty(command)
    unresolved = _unresolved(command)
    now = _timestamp()
    revision: dict[str, object] = {
        "schemaVersion": "1.0",
        "documentType": "research-observatory-research-intent-revision",
        "contractVersion": "1.0.0",
        "intentId": intent_id,
        "revisionId": new_uuid_v7(),
        "revision": revision_number,
        "parentRevision": None
        if prior is None
        else {
            "revisionId": prior["revisionId"],
            "revision": prior["revision"],
            "revisionContentHash": prior["revisionContentHash"],
        },
        "projectId": domain_project_id,
        "revisionContentHash": "sha256:" + "0" * 64,
        "createdAt": now,
        "createdBy": {"actorType": "human", "actorId": actor_id},
        "status": "draft",
        "revisionRationale": command.revision_rationale.strip(),
        "primaryUseCase": command.primary_use_case,
        "epistemicMode": mode,
        "researchQuestion": _statement(command.research_objective),
        "contributionIntent": _statement(command.contribution_intent),
        "phenomenon": _statement(command.phenomenon),
        "unitOfAnalysis": _statement(command.unit_of_analysis),
        "levelOfAnalysis": _statement(command.level_of_analysis),
        "sourceScope": source_scope,
        "evidenceTypes": list(command.evidence_types),
        "noveltyStandard": novelty,
        "autonomy": _autonomy(command.autonomy_level),
        "stoppingRule": {
            "conditions": list(command.stopping_conditions),
            "rationale": "Researcher-selected stopping logic for this epistemic mode.",
            "requiresHumanConfirmation": True,
        },
        "egressPolicy": {"mode": "local-only", "approvedDestinationIds": []},
        "unresolvedDecisions": unresolved,
        "modeRequirements": _mode_requirements(command.primary_use_case, mode),
        "decision": None,
    }
    revision["revisionContentHash"] = _content_hash(revision)
    if decode_research_intent_revision(revision) is None:
        raise _problem(
            status=422,
            code="RO-CORE-INTENT-CONTRACT-INVALID",
            title="Research intent draft is inconsistent",
            detail="The draft does not satisfy the selected mode's versioned intent contract.",
            remediation="Review the use-case, authority, stopping, scope, and novelty selections before retrying.",
        )
    return revision


def _build_acceptance(
    command: IntentAcceptRequest,
    *,
    prior: Mapping[str, object],
    actor_id: str,
) -> dict[str, object]:
    now = _timestamp()
    revision = json.loads(research_intent_snapshot_json(cast(Any, prior)))
    if not isinstance(revision, dict):
        raise RepositoryProblem("research intent acceptance source is invalid")
    revision.update(
        {
            "revisionId": new_uuid_v7(),
            "revision": command.expected_revision + 1,
            "parentRevision": {
                "revisionId": prior["revisionId"],
                "revision": prior["revision"],
                "revisionContentHash": prior["revisionContentHash"],
            },
            "revisionContentHash": "sha256:" + "0" * 64,
            "createdAt": now,
            "createdBy": {"actorType": "human", "actorId": actor_id},
            "status": "accepted",
            "revisionRationale": command.decision_rationale.strip(),
            "decision": {
                "disposition": "accepted",
                "actorType": "human",
                "actorId": actor_id,
                "decidedAt": now,
                "rationale": command.decision_rationale.strip(),
            },
        }
    )
    revision["revisionContentHash"] = _content_hash(revision)
    if decode_research_intent_revision(revision) is None:
        raise _problem(
            status=422,
            code="RO-CORE-INTENT-ACCEPTANCE-CONTRACT-INVALID",
            title="Research intent acceptance is inconsistent",
            detail="The accepted revision does not satisfy the immutable intent contract.",
            remediation="Reload the decision-complete draft and retry its explicit human acceptance.",
        )
    return cast(dict[str, object], revision)


def _governing_reference(revision: Mapping[str, object] | None) -> IntentGoverningReference | None:
    if revision is None:
        return None
    reference = governing_research_intent_reference(revision)
    if reference is None:
        return None
    return IntentGoverningReference.model_validate(reference)


def _projection(revision: Mapping[str, object]) -> IntentDraftProjection:
    source = cast(Mapping[str, object], revision["sourceScope"])
    novelty = cast(Mapping[str, object], revision["noveltyStandard"])
    autonomy = cast(Mapping[str, object], revision["autonomy"])
    stopping = cast(Mapping[str, object], revision["stoppingRule"])
    unresolved = tuple(cast(Sequence[str], revision["unresolvedDecisions"]))
    temporal = cast(Mapping[str, object], source.get("temporalCoverage", {}))
    accepted = revision["status"] == "accepted"
    return IntentDraftProjection(
        intent_id=cast(str, revision["intentId"]),
        revision_id=cast(str, revision["revisionId"]),
        revision=cast(int, revision["revision"]),
        revision_content_hash=cast(str, revision["revisionContentHash"]),
        created_at=cast(str, revision["createdAt"]),
        status=cast(Any, revision["status"]),
        primary_use_case=cast(Any, revision["primaryUseCase"]),
        epistemic_mode=cast(Any, revision["epistemicMode"]),
        research_objective=_specified_value(revision["researchQuestion"]),
        contribution_intent=_specified_value(revision["contributionIntent"]),
        phenomenon=_specified_value(revision["phenomenon"]),
        unit_of_analysis=_specified_value(revision["unitOfAnalysis"]),
        level_of_analysis=_specified_value(revision["levelOfAnalysis"]),
        source_kinds=tuple(cast(Sequence[Any], source.get("sourceKinds", ()))),
        language_codes=tuple(cast(Sequence[str], source.get("languages", ()))),
        start_year=cast(int | None, temporal.get("startYear")),
        end_year=cast(int | None, temporal.get("endYear")),
        include_private_reports=source.get("privateReports") == "allowed",
        evidence_types=tuple(cast(Sequence[Any], revision["evidenceTypes"])),
        novelty_standard=cast(Any, novelty.get("standard")),
        novelty_rationale=cast(str, novelty.get("rationale", "")) if novelty.get("state") == "specified" else "",
        autonomy_level=cast(Any, autonomy["level"]),
        stopping_conditions=tuple(cast(Sequence[Any], stopping["conditions"])),
        revision_rationale=cast(str, revision["revisionRationale"]),
        unresolved_decisions=unresolved,
        decision_complete=not unresolved,
        can_request_acceptance=not unresolved and not accepted,
        launch_ready=accepted,
    )


def _summary(revision: Mapping[str, object]) -> IntentRevisionSummary:
    unresolved = cast(Sequence[object], revision["unresolvedDecisions"])
    return IntentRevisionSummary(
        revision=cast(int, revision["revision"]),
        revision_id=cast(str, revision["revisionId"]),
        revision_content_hash=cast(str, revision["revisionContentHash"]),
        created_at=cast(str, revision["createdAt"]),
        status=cast(Any, revision["status"]),
        primary_use_case=cast(Any, revision["primaryUseCase"]),
        unresolved_decision_count=len(unresolved),
    )


def _decoded_records(records: tuple[IntentRevisionRecord, ...]) -> tuple[Mapping[str, object], ...]:
    decoded: list[Mapping[str, object]] = []
    for record in records:
        try:
            value = json.loads(record.content_json)
        except json.JSONDecodeError, TypeError:
            raise RepositoryProblem("research intent JSON is invalid") from None
        snapshot = decode_research_intent_revision(value)
        if snapshot is None or snapshot["revision"] != record.revision:
            raise RepositoryProblem("research intent contract is invalid")
        decoded.append(cast(Mapping[str, object], snapshot))
    for current, prior in pairwise(decoded):
        parent = cast(Mapping[str, object], current["parentRevision"])
        if (
            current["intentId"] != prior["intentId"]
            or current["projectId"] != prior["projectId"]
            or parent["revisionId"] != prior["revisionId"]
            or parent["revision"] != prior["revision"]
            or parent["revisionContentHash"] != prior["revisionContentHash"]
        ):
            raise RepositoryProblem("research intent history is inconsistent")
    return tuple(decoded)


def _authority_records(records: tuple[WorkflowAuthorityRecord, ...]) -> tuple[Mapping[str, object], ...]:
    decoded: list[Mapping[str, object]] = []
    for record in records:
        try:
            value = json.loads(record.content_json)
        except json.JSONDecodeError, TypeError:
            raise RepositoryProblem("workflow authority JSON is invalid") from None
        if not isinstance(value, dict):
            raise RepositoryProblem("workflow authority record is invalid")
        decoded.append(value)
    return tuple(decoded)


def _validated_workflow_authority(
    authority: WorkflowAuthorityMutation,
) -> tuple[tuple[Mapping[str, object], ...], tuple[Mapping[str, object], ...]]:
    selections = _authority_records(authority.selections)
    migrations = _authority_records(authority.migrations)
    decisions = _authority_records(authority.decisions)
    if authority.activation is None:
        if selections or authority.activation_witness is not None:
            raise RepositoryProblem("workflow authority activation is missing")
    else:
        activation_records = _authority_records((authority.activation,))
        activation = activation_records[0]
        first_selection = selections[0] if selections else None
        first_intent = first_selection.get("researchIntent") if first_selection is not None else None
        first_selector = first_selection.get("selectedBy") if first_selection is not None else None
        expected_fields = {
            "schemaVersion",
            "documentType",
            "authority",
            "domainProjectId",
            "activatedAtIntentRevision",
            "firstSelectionRevisionId",
            "firstSelectionContentHash",
            "profileCatalogHash",
            "intentGuidanceVersion",
            "intentGuidanceHash",
            "activationWitnessEventId",
            "bindingContentHash",
        }
        witness = authority.activation_witness
        if (
            authority.activation.revision != 0
            or not selections
            or witness is None
            or set(activation) != expected_fields
            or activation.get("schemaVersion") != "1.1"
            or activation.get("documentType") != "research-observatory-workflow-authority-binding"
            or activation.get("authority") != "ADR-0026"
            or activation.get("profileCatalogHash") != APPROVED_WORKFLOW_PROFILE_CATALOG_SHA256
            or activation.get("intentGuidanceVersion") != INTENT_PROFILE_GUIDANCE_VERSION
            or activation.get("intentGuidanceHash") != APPROVED_INTENT_PROFILE_GUIDANCE_SHA256
            or activation.get("bindingContentHash") != _authority_content_hash(activation, "bindingContentHash")
            or first_selection is None
            or not isinstance(first_intent, Mapping)
            or not isinstance(first_selector, Mapping)
            or activation.get("domainProjectId") != first_selection.get("projectId")
            or activation.get("activatedAtIntentRevision") != first_intent.get("revision")
            or activation.get("firstSelectionRevisionId") != first_selection.get("selectionRevisionId")
            or activation.get("firstSelectionContentHash") != first_selection.get("revisionContentHash")
            or activation.get("activationWitnessEventId") != witness.event_id
            or witness.occurred_at != first_selection.get("createdAt")
            or witness.actor_id != first_selector.get("actorId")
            or witness.record_sha256 != hashlib.sha256(authority.activation.content_json.encode("utf-8")).hexdigest()
        ):
            raise RepositoryProblem("workflow authority activation is invalid")
    if [record.revision for record in authority.selections] != list(range(1, len(authority.selections) + 1)):
        raise RepositoryProblem("workflow selection history is discontinuous")
    for record, selection in zip(authority.selections, selections, strict=True):
        if selection.get("revision") != record.revision:
            raise RepositoryProblem("workflow selection revision differs")
        if selection.get("revisionContentHash") != _authority_content_hash(selection, "revisionContentHash"):
            raise RepositoryProblem("workflow selection content hash differs")
        if decode_project_workflow_selection(_WORKFLOW_CATALOG, selection) is None:
            raise RepositoryProblem("workflow selection contract is invalid")
    for previous, current in pairwise(selections):
        if _canonical_json(current["parentSelection"]) != _canonical_json(_parent_selection(previous)):
            raise RepositoryProblem("workflow selection predecessor lookup differs")
    for record, migration in zip(authority.migrations, migrations, strict=True):
        if migration.get("migrationContentHash") != _authority_content_hash(migration, "migrationContentHash"):
            raise RepositoryProblem("workflow migration content hash differs")
        if decode_workflow_profile_migration(_WORKFLOW_CATALOG, migration) is None:
            raise RepositoryProblem("workflow migration contract is invalid")
        if record.revision < 2:
            raise RepositoryProblem("workflow migration revision is invalid")
    for record, decision in zip(authority.decisions, decisions, strict=True):
        if (
            set(decision) != {"decisionId", "decisionContentHash", "decision", "decidedAt", "decidedBy"}
            or decision.get("decision") != "accepted"
            or decision.get("decisionContentHash") != _authority_content_hash(decision, "decisionContentHash")
            or record.revision < 2
        ):
            raise RepositoryProblem("workflow acceptance decision is invalid")
    if (
        len(migrations) != max(0, len(selections) - 1)
        or len(decisions) != len(migrations)
        or [record.revision for record in authority.migrations]
        != [cast(int, selection["revision"]) for selection in selections[1:]]
        or [record.revision for record in authority.decisions]
        != [cast(int, selection["revision"]) for selection in selections[1:]]
    ):
        raise RepositoryProblem("workflow migration or acceptance history is discontinuous")
    for selection in selections[1:]:
        accepted = cast(Mapping[str, object], selection["acceptedMigration"])
        matching_migrations = [
            migration
            for migration in migrations
            if migration["migrationId"] == accepted["migrationId"]
            and migration["migrationContentHash"] == accepted["migrationContentHash"]
        ]
        acceptance = cast(Mapping[str, object], accepted["acceptance"])
        matching_decisions = [
            decision
            for decision in decisions
            if decision["decisionId"] == acceptance["decisionId"]
            and decision["decisionContentHash"] == acceptance["decisionContentHash"]
        ]
        if (
            len(matching_migrations) != 1
            or len(matching_decisions) != 1
            or _canonical_json(matching_migrations[0]["acceptance"]) != _canonical_json(matching_decisions[0])
        ):
            raise RepositoryProblem("workflow migration or acceptance lookup differs")
    return selections, migrations


def _validate_intent_authority_references(
    revisions: tuple[Mapping[str, object], ...],
    selections: tuple[Mapping[str, object], ...],
    migrations: tuple[Mapping[str, object], ...],
) -> None:
    canonical_by_reference = {_canonical_json(_intent_reference(revision)): revision for revision in revisions}

    def require_reference(value: object) -> Mapping[str, object]:
        if not isinstance(value, Mapping):
            raise RepositoryProblem("workflow intent reference is invalid")
        revision = canonical_by_reference.get(_canonical_json(value))
        if revision is None:
            raise RepositoryProblem("workflow intent reference does not resolve to canonical history")
        return revision

    for selection in selections:
        revision = require_reference(selection.get("researchIntent"))
        if (
            selection.get("projectId") != revision.get("projectId")
            or cast(Mapping[str, object], selection["profile"]).get("profileId") != revision.get("primaryUseCase")
            or selection.get("selectedBy") != revision.get("createdBy")
        ):
            raise RepositoryProblem("workflow selection differs from canonical intent authority")

    for migration in migrations:
        prior = require_reference(migration.get("priorResearchIntent"))
        target = require_reference(migration.get("targetResearchIntent"))
        acceptance = migration.get("acceptance")
        if not isinstance(acceptance, Mapping):
            raise RepositoryProblem("workflow migration acceptance is invalid")
        if (
            cast(int, target["revision"]) != cast(int, prior["revision"]) + 1
            or target.get("intentId") != prior.get("intentId")
            or target.get("projectId") != prior.get("projectId")
            or migration.get("createdBy") != target.get("createdBy")
            or acceptance.get("decidedBy") != target.get("createdBy")
        ):
            raise RepositoryProblem("workflow migration differs from canonical intent authority")


def _scope_from_projection(projection: IntentDraftProjection) -> dict[str, object]:
    return {
        "primaryUseCase": projection.primary_use_case,
        "sourceKinds": list(projection.source_kinds),
        "languageCodes": list(projection.language_codes),
        "startYear": projection.start_year,
        "endYear": projection.end_year,
        "includePrivateReports": projection.include_private_reports,
        "evidenceTypes": list(projection.evidence_types),
        "noveltyStandard": projection.novelty_standard,
        "autonomyLevel": projection.autonomy_level,
        "stoppingConditions": list(projection.stopping_conditions),
    }


def _scope_from_request(command: IntentImpactRequest) -> dict[str, object]:
    return {
        "primaryUseCase": command.primary_use_case,
        "sourceKinds": list(command.source_kinds),
        "languageCodes": list(command.language_codes),
        "startYear": command.start_year,
        "endYear": command.end_year,
        "includePrivateReports": command.include_private_reports,
        "evidenceTypes": list(command.evidence_types),
        "noveltyStandard": command.novelty_standard,
        "autonomyLevel": command.autonomy_level,
        "stoppingConditions": list(command.stopping_conditions),
    }


def _impact(
    current: IntentDraftProjection | None,
    command: IntentImpactRequest,
    *,
    stale_artifact_ids: tuple[str, ...] = (),
) -> IntentImpactPreview:
    if current is None:
        return IntentImpactPreview(
            expected_revision=command.expected_revision,
            change_categories=(),
            affected_workflows=(),
            affected_outputs=(),
            affected_schemas=(),
            affected_checkpoints=(),
            autonomy_default_effects=(),
            stopping_logic_effects=(),
            stale_artifact_ids=(),
            warnings=(),
            acknowledgement_required=False,
            acknowledgement_token=None,
        )
    before = _scope_from_projection(current)
    after = _scope_from_request(command)
    categories: list[str] = []
    if before["primaryUseCase"] != after["primaryUseCase"]:
        categories.append("primary-use-case")
    if any(
        before[key] != after[key]
        for key in ("sourceKinds", "languageCodes", "startYear", "endYear", "includePrivateReports")
    ):
        categories.append("corpus-scope")
    if before["noveltyStandard"] != after["noveltyStandard"]:
        categories.append("novelty-scope")
    if not categories:
        return IntentImpactPreview(
            expected_revision=command.expected_revision,
            change_categories=(),
            affected_workflows=(),
            affected_outputs=(),
            affected_schemas=(),
            affected_checkpoints=(),
            autonomy_default_effects=(),
            stopping_logic_effects=(),
            stale_artifact_ids=(),
            warnings=(),
            acknowledgement_required=False,
            acknowledgement_token=None,
        )
    old_case = current.primary_use_case
    new_case = command.primary_use_case
    old_profile = _PROFILE_BY_ID[old_case]
    new_profile = _PROFILE_BY_ID[new_case]
    old_stages = cast(Sequence[Mapping[str, object]], old_profile["stages"])
    new_stages = cast(Sequence[Mapping[str, object]], new_profile["stages"])
    workflows = tuple(
        dict.fromkeys(_stage_label(cast(str, stage["pageContractId"])) for stage in (*old_stages, *new_stages))
    )
    outputs = tuple(
        dict.fromkeys(
            (
                *cast(Sequence[str], old_profile["expectedOutputs"]),
                *cast(Sequence[str], new_profile["expectedOutputs"]),
            )
        )
    )
    schemas = ["research-intent-revision"]
    checkpoints: tuple[str, ...] = ()
    autonomy_effects: tuple[str, ...] = ()
    stopping_effects: tuple[str, ...] = ()
    if "primary-use-case" in categories:
        schemas.extend(("project-workflow-selection", "workflow-profile-migration"))
        old_positions = {cast(str, stage["stageKey"]): cast(int, stage["order"]) for stage in old_stages}
        new_positions = {cast(str, stage["stageKey"]): cast(int, stage["order"]) for stage in new_stages}
        checkpoints = tuple(
            dict.fromkeys(
                _stage_label(cast(str, stage["pageContractId"]))
                for stage in (*old_stages, *new_stages)
                if old_positions.get(cast(str, stage["stageKey"])) != new_positions.get(cast(str, stage["stageKey"]))
            )
        )
        if before["autonomyLevel"] == after["autonomyLevel"]:
            autonomy_effects = (f"retained autonomy level: {after['autonomyLevel']}",)
        else:
            autonomy_effects = (
                f"removed autonomy level: {before['autonomyLevel']}",
                f"added autonomy level: {after['autonomyLevel']}",
            )
        before_stopping = cast(Sequence[str], before["stoppingConditions"])
        after_stopping = cast(Sequence[str], after["stoppingConditions"])
        stopping_effects = tuple(
            [
                f"retained stopping condition: {condition}"
                for condition in before_stopping
                if condition in after_stopping
            ]
            + [
                f"removed stopping condition: {condition}"
                for condition in before_stopping
                if condition not in after_stopping
            ]
            + [
                f"added stopping condition: {condition}"
                for condition in after_stopping
                if condition not in before_stopping
            ]
        )
    warnings: list[str] = []
    if "primary-use-case" in categories:
        warnings.append(
            "Ordered workflow, validation checkpoints, and expected outputs will change after human acceptance."
        )
    if "corpus-scope" in categories:
        warnings.append(
            "Corpus-dependent searches, screening decisions, and evidence outputs require impact review; "
            "prior work is retained."
        )
    if "novelty-scope" in categories:
        warnings.append(
            "Novelty and opportunity claims require renewed nearest-prior-work review; "
            "prior conclusions are not deleted."
        )
    token_payload = {
        "affectedCheckpoints": checkpoints,
        "affectedSchemas": schemas,
        "autonomyDefaultEffects": autonomy_effects,
        "baseRevisionContentHash": current.revision_content_hash,
        "categories": categories,
        "expectedRevision": command.expected_revision,
        "scope": after,
        "staleArtifactIds": list(stale_artifact_ids),
        "stoppingLogicEffects": stopping_effects,
    }
    token = hashlib.sha256(_canonical_json(token_payload).encode("utf-8")).hexdigest()
    return IntentImpactPreview(
        expected_revision=command.expected_revision,
        change_categories=cast(Any, tuple(categories)),
        affected_workflows=workflows,
        affected_outputs=outputs,
        affected_schemas=tuple(schemas),
        affected_checkpoints=checkpoints,
        autonomy_default_effects=autonomy_effects,
        stopping_logic_effects=stopping_effects,
        stale_artifact_ids=stale_artifact_ids,
        warnings=tuple(warnings),
        acknowledgement_required=True,
        acknowledgement_token=token,
    )


def _policy_decision(
    command: IntentPolicyRequest,
    *,
    accepted: Mapping[str, object] | None,
) -> IntentPolicyDecision:
    decision_id = new_uuid_v7()
    evaluated_at = _timestamp()
    governing = _governing_reference(accepted)
    if accepted is None or governing is None:
        return IntentPolicyDecision(
            decision_id=decision_id,
            evaluated_at=evaluated_at,
            action=command.action,
            subject_type=command.subject_type,
            outcome="deny",
            reason_code="no-active-accepted-intent",
            explanation="Consequential work is denied because the project has no valid accepted intent revision.",
            governing_intent=None,
            required_gates=(),
            output_label=None,
            stopping_requires_human_confirmation=True,
        )
    mode = cast(str, accepted["epistemicMode"])
    autonomy = cast(Mapping[str, object], accepted["autonomy"])
    allowed = set(cast(Sequence[str], autonomy["allowedActions"]))
    selected_stopping = set(cast(Sequence[str], cast(Mapping[str, object], accepted["stoppingRule"])["conditions"]))
    output_label = cast(Any, _OUTPUT_LABELS[mode])
    required_gates: tuple[Any, ...] = ()
    outcome = "allow"
    reason = "active-intent-allows-action"
    explanation = "The action is permitted by the active accepted intent and is bound to its governing reference."

    if command.action == "external-egress":
        outcome = "deny"
        reason = "active-intent-prohibits-external-egress"
        explanation = (
            "The active intent is local-only, so an external-egress gate cannot be bypassed or self-authorized."
        )
        required_gates = ("external-egress",)
    elif command.action in _GATE_ACTIONS:
        gate = cast(Any, _GATE_ACTIONS[command.action])
        outcome = "require-confirmation"
        reason = f"{gate}-requires-human-confirmation"
        explanation = (
            f"The {gate} gate remains under explicit human authority and cannot be satisfied by policy evaluation."
        )
        required_gates = (gate,)
    elif command.action in {"recommend-stopping", "confirm-stopping"}:
        if command.stopping_condition is None or command.stopping_condition not in selected_stopping:
            outcome = "deny"
            reason = "stopping-condition-not-governed"
            explanation = "The requested stopping condition is absent from the active intent revision."
        elif command.stopping_condition == "resource-budget" and len(selected_stopping) == 1:
            outcome = "deny"
            reason = "resource-budget-cannot-be-sole-stopping-rule"
            explanation = "A resource budget is secondary and cannot independently establish scholarly completion."
        else:
            outcome = "recommend-human" if command.action == "recommend-stopping" else "require-confirmation"
            reason = "stopping-requires-human-confirmation"
            explanation = (
                "The selected mode-specific stopping condition may be reported, but only a human may confirm stopping."
            )
    elif command.subject_type != "human" and command.action not in allowed:
        outcome = "deny"
        reason = "autonomy-level-prohibits-action"
        explanation = "The active intent autonomy level does not permit this model or system action."
    elif command.action == "prepare-draft-output":
        required_gates = ("claim-approval", "publication")
        explanation = "A labeled working draft may be prepared; claim approval and publication remain human gates."

    return IntentPolicyDecision(
        decision_id=decision_id,
        evaluated_at=evaluated_at,
        action=command.action,
        subject_type=command.subject_type,
        outcome=cast(Any, outcome),
        reason_code=reason,
        explanation=explanation,
        governing_intent=governing,
        required_gates=required_gates,
        output_label=None if outcome == "deny" else output_label,
        stopping_requires_human_confirmation=True,
    )


class ResearchIntentService:
    """Project-scoped application service for non-governing draft revisions."""

    def __init__(
        self,
        projects: ProjectLifecycleService,
        *,
        repository_factory: _RepositoryFactory,
        stale_state_repository_factory: _StaleStateRepositoryFactory,
        local_actor_id: str | None,
    ) -> None:
        if local_actor_id is not None and not is_uuid_v7(local_actor_id):
            raise ValueError("local actor identity must be a UUIDv7")
        self._projects = projects
        self._repository_factory = repository_factory
        self._stale_state_repository_factory = stale_state_repository_factory
        self._local_actor_id = local_actor_id
        self._policy_cache: dict[str, Mapping[str, object] | None] = {}
        self._policy_cache_lock = RLock()

    @classmethod
    def unavailable(cls, projects: ProjectLifecycleService) -> ResearchIntentService:
        return cls(
            projects,
            repository_factory=lambda _path, _project_id: _UnavailableIntentRepository(),
            stale_state_repository_factory=lambda _path, _project_id: _UnavailableStaleStateRepository(),
            local_actor_id=None,
        )

    def workflow_profile_catalog(self) -> WorkflowProfileCatalogProjection:
        return _workflow_catalog_projection()

    def initialize_created_project(
        self,
        path: Path,
        manifest_project_id: str,
        *,
        primary_use_case: str,
        research_objective: str,
        trace_id: str,
    ) -> None:
        actor_id = self._local_actor_id
        if actor_id is None:
            raise ProjectLifecycleProblem(
                status=503,
                code="RO-CORE-INTENT-ACTOR-UNAVAILABLE",
                title="Local researcher identity is unavailable",
                detail="Project creation stopped before publication because local actor authority is unavailable.",
                remediation="Restore the current-user profile vault and retry project creation.",
                retryable=True,
            )
        try:
            command = IntentDraftRequest(
                root=str(path),
                expected_revision=0,
                primary_use_case=cast(Any, primary_use_case),
                research_objective=research_objective.strip(),
                contribution_intent="",
                phenomenon="",
                unit_of_analysis="",
                level_of_analysis="",
                source_kinds=(),
                language_codes=(),
                start_year=None,
                end_year=None,
                include_private_reports=False,
                evidence_types=(),
                novelty_standard=None,
                novelty_rationale="",
                autonomy_level="human-only",
                stopping_conditions=("researcher-decision",),
                revision_rationale="Project creation selected the initial governed workflow profile.",
                impact_acknowledgement=None,
            )
            idempotency_key = hashlib.sha256(
                _canonical_json(
                    {
                        "actorId": actor_id,
                        "manifestProjectId": manifest_project_id,
                        "primaryUseCase": primary_use_case,
                        "researchObjective": research_objective.strip(),
                    }
                ).encode("utf-8")
            ).hexdigest()[:32]
            self._save(
                self._repository_factory(path, manifest_project_id),
                self._stale_state_repository_factory(path, manifest_project_id),
                manifest_project_id,
                command,
                trace_id=trace_id,
                idempotency_key=idempotency_key,
                actor_id=actor_id,
            )
        except IntentProblem as error:
            raise ProjectLifecycleProblem(
                status=error.status,
                code=error.code,
                title=error.title,
                detail=error.detail,
                remediation=error.remediation,
                retryable=error.retryable,
            ) from error

    def workspace(self, root: str) -> IntentWorkspaceProjection:
        return self._projects.perform_open_project_action(
            root=root,
            require_write=False,
            action=lambda path, project_id: self._workspace(self._repository_factory(path, project_id), project_id),
        )

    def preview(self, command: IntentImpactRequest) -> IntentImpactPreview:
        return self._projects.perform_open_project_action(
            root=command.root,
            require_write=False,
            action=lambda path, project_id: self._preview(
                self._repository_factory(path, project_id),
                self._stale_state_repository_factory(path, project_id),
                project_id,
                command,
            ),
        )

    def save_draft(
        self,
        command: IntentDraftRequest,
        *,
        trace_id: str,
        idempotency_key: str,
    ) -> IntentDraftProjection:
        actor_id = self._local_actor_id
        if actor_id is None:
            raise _problem(
                status=503,
                code="RO-CORE-INTENT-ACTOR-UNAVAILABLE",
                title="Local researcher identity is unavailable",
                detail="The current Windows profile could not supply the stable local actor authority.",
                remediation="Restore the current-user profile vault before saving an intent revision.",
                retryable=True,
            )
        return self._projects.perform_open_project_action(
            root=command.root,
            require_write=True,
            action=lambda path, project_id: self._save(
                self._repository_factory(path, project_id),
                self._stale_state_repository_factory(path, project_id),
                project_id,
                command,
                trace_id=trace_id,
                idempotency_key=idempotency_key,
                actor_id=actor_id,
            ),
        )

    def accept(
        self,
        command: IntentAcceptRequest,
        *,
        trace_id: str,
        idempotency_key: str,
    ) -> IntentDraftProjection:
        actor_id = self._require_actor()
        return self._projects.perform_open_project_action(
            root=command.root,
            require_write=True,
            action=lambda path, project_id: self._accept(
                self._repository_factory(path, project_id),
                project_id,
                command,
                trace_id=trace_id,
                idempotency_key=idempotency_key,
                actor_id=actor_id,
            ),
        )

    def evaluate_policy(self, command: IntentPolicyRequest, *, trace_id: str) -> IntentPolicyDecision:
        actor_id = self._require_actor()
        return self._projects.perform_open_project_action(
            root=command.root,
            require_write=True,
            action=lambda path, project_id: self._evaluate_policy(
                self._repository_factory(path, project_id),
                project_id,
                command,
                trace_id=trace_id,
                actor_id=actor_id,
            ),
        )

    def _require_actor(self) -> str:
        if self._local_actor_id is None:
            raise _problem(
                status=503,
                code="RO-CORE-INTENT-ACTOR-UNAVAILABLE",
                title="Local researcher identity is unavailable",
                detail="The current Windows profile could not supply the stable local actor authority.",
                remediation="Restore the current-user profile vault before changing or evaluating intent policy.",
                retryable=True,
            )
        return self._local_actor_id

    def _read(self, repository: IntentRevisionRepository) -> tuple[Mapping[str, object], ...]:
        try:
            return _decoded_records(repository.read())
        except RepositoryProblem as error:
            raise _problem(
                status=500,
                code="RO-CORE-INTENT-READ-FAILED",
                title="Research intent is unavailable",
                detail="The local intent revision history could not be validated.",
                remediation="Keep consequential analysis stopped and run project health checks before retrying.",
                retryable=True,
            ) from error

    def _read_workflow_authority(
        self,
        repository: IntentRevisionRepository,
        revisions: tuple[Mapping[str, object], ...],
    ) -> WorkflowAuthorityMutation:
        try:
            authority = repository.read_workflow_authority()
            selections, migrations = _validated_workflow_authority(authority)
            _validate_intent_authority_references(revisions, selections, migrations)
        except RepositoryProblem as error:
            raise _problem(
                status=500,
                code="RO-CORE-WORKFLOW-PROFILE-READ-FAILED",
                title="Workflow profile authority is unavailable",
                detail="The immutable workflow selection, migration, or acceptance history could not be validated.",
                remediation="Keep navigation stopped and run project health checks before retrying.",
                retryable=True,
            ) from error
        if selections and revisions:
            latest_selection = selections[-1]
            latest_intent = revisions[0]
            if (
                latest_selection["projectId"] != latest_intent["projectId"]
                or cast(Mapping[str, object], latest_selection["profile"])["profileId"]
                != latest_intent["primaryUseCase"]
            ):
                raise _problem(
                    status=500,
                    code="RO-CORE-WORKFLOW-PROFILE-READ-FAILED",
                    title="Workflow profile authority is unavailable",
                    detail="The latest workflow selection does not match the current Research Intent authority.",
                    remediation="Keep navigation stopped and run project health checks before retrying.",
                )
        return authority

    def _workspace(
        self,
        repository: IntentRevisionRepository,
        project_id: str,
    ) -> IntentWorkspaceProjection:
        revisions = self._read(repository)
        self._read_workflow_authority(repository, revisions)
        return IntentWorkspaceProjection(
            project_id=project_id,
            current=_projection(revisions[0]) if revisions else None,
            history=tuple(_summary(revision) for revision in revisions[:_MAX_HISTORY]),
        )

    def _preview(
        self,
        repository: IntentRevisionRepository,
        stale_state_repository: _StaleStateRepository,
        _project_id: str,
        command: IntentImpactRequest,
    ) -> IntentImpactPreview:
        revisions = self._read(repository)
        self._read_workflow_authority(repository, revisions)
        current = _projection(revisions[0]) if revisions else None
        current_revision = current.revision if current is not None else 0
        if command.expected_revision != current_revision:
            raise _problem(
                status=409,
                code="RO-CORE-INTENT-REVISION-CONFLICT",
                title="Research intent changed",
                detail="The impact preview was based on an older local intent revision.",
                remediation="Reload the current revision, review its scope, and preview the changes again.",
            )
        preview = _impact(current, command)
        if not preview.acknowledgement_required:
            return preview
        return _impact(
            current,
            command,
            stale_artifact_ids=self._stale_artifact_ids(stale_state_repository),
        )

    def _stale_artifact_ids(self, repository: _StaleStateRepository) -> tuple[str, ...]:
        try:
            return tuple(dict.fromkeys(state.output_revision_id for state in repository.stale_states()))
        except RepositoryProblem as error:
            raise _problem(
                status=500,
                code="RO-CORE-INTENT-IMPACT-STALE-STATE-READ-FAILED",
                title="Intent change impact is unavailable",
                detail="Known stale artifact state could not be validated for the impact preview.",
                remediation="Keep the prior intent authoritative and run project health checks before retrying.",
                retryable=True,
            ) from error

    def _accept(
        self,
        repository: IntentRevisionRepository,
        manifest_project_id: str,
        command: IntentAcceptRequest,
        *,
        trace_id: str,
        idempotency_key: str,
        actor_id: str,
    ) -> IntentDraftProjection:
        if not command.confirmed:
            raise _problem(
                status=409,
                code="RO-CORE-INTENT-ACCEPTANCE-CONFIRMATION-REQUIRED",
                title="Intent acceptance requires human confirmation",
                detail="The intent-acceptance gate cannot be bypassed by an unconfirmed request.",
                remediation="Review the exact decision-complete revision and explicitly confirm its acceptance.",
            )
        with self._policy_cache_lock:
            return self._accept_locked(
                repository,
                manifest_project_id,
                command,
                trace_id=trace_id,
                idempotency_key=idempotency_key,
                actor_id=actor_id,
            )

    def _accept_locked(
        self,
        repository: IntentRevisionRepository,
        manifest_project_id: str,
        command: IntentAcceptRequest,
        *,
        trace_id: str,
        idempotency_key: str,
        actor_id: str,
    ) -> IntentDraftProjection:
        command_sha256 = _accept_command_sha256(
            command,
            manifest_project_id=manifest_project_id,
            actor_id=actor_id,
        )
        try:
            replay = repository.replay(
                manifest_project_id=manifest_project_id,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                command_sha256=command_sha256,
                event_type="intent.accepted",
            )
        except RepositoryIdempotencyConflict as error:
            raise _problem(
                status=409,
                code="RO-CORE-INTENT-IDEMPOTENCY-CONFLICT",
                title="Intent command key was already used",
                detail="The idempotency key is bound to a different project, actor, or intent command.",
                remediation="Do not reuse command keys. Reload the project and issue a new key for a new command.",
            ) from error
        except RepositoryProblem as error:
            raise _problem(
                status=500,
                code="RO-CORE-INTENT-WRITE-FAILED",
                title="Research intent was not accepted",
                detail="The local idempotency authority could not be validated.",
                remediation="The prior governing revision remains authoritative. Run project health checks.",
                retryable=True,
            ) from error
        if replay is not None:
            replayed = _decoded_records((replay,))[0]
            revisions = self._read(repository)
            self._read_workflow_authority(repository, revisions)
            self._policy_cache[manifest_project_id] = next(
                (revision for revision in revisions if revision["status"] == "accepted"),
                None,
            )
            return _projection(replayed)

        revisions = self._read(repository)
        self._read_workflow_authority(repository, revisions)
        if not revisions:
            raise _problem(
                status=409,
                code="RO-CORE-INTENT-ACCEPTANCE-DRAFT-REQUIRED",
                title="A decision-complete draft is required",
                detail="No research intent draft exists for human acceptance.",
                remediation="Save and review a decision-complete draft before accepting it.",
            )
        prior = revisions[0]
        current = _projection(prior)
        if (
            current.status != "draft"
            or not current.decision_complete
            or command.expected_revision != current.revision
            or command.expected_revision_content_hash != current.revision_content_hash
        ):
            raise _problem(
                status=409,
                code="RO-CORE-INTENT-ACCEPTANCE-REVISION-CONFLICT",
                title="Intent acceptance is not bound to the current draft",
                detail=(
                    "The requested revision is incomplete, already decided, or differs from the exact current draft."
                ),
                remediation="Reload and review the current decision-complete draft before confirming acceptance.",
            )
        revision = _build_acceptance(command, prior=prior, actor_id=actor_id)
        content_json = _canonical_json(revision)
        digest = hashlib.sha256(content_json.encode("utf-8")).hexdigest()
        event = IntentAuditEvent(
            event_id=new_uuid_v7(),
            outbox_id=new_uuid_v7(),
            event_type="intent.accepted",
            occurred_at=cast(str, revision["createdAt"]),
            trace_id=trace_id,
            actor_type="human",
            actor_id=actor_id,
            record_sha256=digest,
            command_sha256=command_sha256,
            idempotency_key=idempotency_key,
        )
        try:
            committed = repository.append(
                expected_revision=current.revision,
                domain_project_id=cast(str, prior["projectId"]),
                manifest_project_id=manifest_project_id,
                record=IntentRevisionRecord(revision=current.revision + 1, content_json=content_json),
                event=event,
            )
        except RepositoryConflict as error:
            raise _problem(
                status=409,
                code="RO-CORE-INTENT-ACCEPTANCE-REVISION-CONFLICT",
                title="Research intent changed before acceptance",
                detail="Another local command committed the next intent revision first.",
                remediation="Reload and review the current revision before accepting it.",
            ) from error
        except RepositoryProblem as error:
            raise _problem(
                status=500,
                code="RO-CORE-INTENT-WRITE-FAILED",
                title="Research intent was not accepted",
                detail="The accepted revision, provenance fact, and outbox event did not commit atomically.",
                remediation="The prior revision remains authoritative. Run project health checks before retrying.",
                retryable=True,
            ) from error
        accepted = _decoded_records((committed,))[0]
        self._policy_cache[manifest_project_id] = accepted
        emit_log_record(
            "intent.accepted",
            level="INFO",
            fields={"reasonCode": "intent-human-accepted", "traceId": trace_id},
        )
        return _projection(accepted)

    def _evaluate_policy(
        self,
        repository: IntentRevisionRepository,
        manifest_project_id: str,
        command: IntentPolicyRequest,
        *,
        trace_id: str,
        actor_id: str,
    ) -> IntentPolicyDecision:
        with self._policy_cache_lock:
            return self._evaluate_policy_locked(
                repository,
                manifest_project_id,
                command,
                trace_id=trace_id,
                actor_id=actor_id,
            )

    def _evaluate_policy_locked(
        self,
        repository: IntentRevisionRepository,
        manifest_project_id: str,
        command: IntentPolicyRequest,
        *,
        trace_id: str,
        actor_id: str,
    ) -> IntentPolicyDecision:
        if manifest_project_id not in self._policy_cache:
            revisions = self._read(repository)
            self._policy_cache[manifest_project_id] = next(
                (revision for revision in revisions if revision["status"] == "accepted"),
                None,
            )
        accepted = self._policy_cache[manifest_project_id]
        decision = _policy_decision(command, accepted=accepted)
        audit_value = {
            "actorId": actor_id,
            "decision": decision.model_dump(mode="json", by_alias=True),
            "decisionId": decision.decision_id,
            "eventType": "intent.policy.evaluated",
            "schemaVersion": "1.0",
        }
        content_json = _canonical_json(audit_value)
        try:
            repository.append_policy_decision(
                record=IntentPolicyDecisionRecord(decision_id=decision.decision_id, content_json=content_json),
                event=IntentPolicyAuditEvent(
                    event_id=new_uuid_v7(),
                    occurred_at=decision.evaluated_at,
                    trace_id=trace_id,
                    actor_type="human",
                    actor_id=actor_id,
                    record_sha256=hashlib.sha256(content_json.encode("utf-8")).hexdigest(),
                ),
            )
        except RepositoryProblem as error:
            raise _problem(
                status=500,
                code="RO-CORE-INTENT-POLICY-AUDIT-FAILED",
                title="Intent policy decision is unavailable",
                detail="The content-free policy decision and its provenance fact could not be committed atomically.",
                remediation="Keep the requested action stopped and run project health checks before retrying.",
                retryable=True,
            ) from error
        emit_log_record(
            "intent.policy.evaluated",
            level="INFO",
            fields={"reasonCode": decision.reason_code, "traceId": trace_id},
        )
        return decision

    def _save(
        self,
        repository: IntentRevisionRepository,
        stale_state_repository: _StaleStateRepository,
        manifest_project_id: str,
        command: IntentDraftRequest,
        *,
        trace_id: str,
        idempotency_key: str,
        actor_id: str,
    ) -> IntentDraftProjection:
        command_sha256 = _command_sha256(
            command,
            manifest_project_id=manifest_project_id,
            actor_id=actor_id,
        )
        try:
            replay = repository.replay(
                manifest_project_id=manifest_project_id,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                command_sha256=command_sha256,
                event_type="intent.draft.saved",
            )
        except RepositoryIdempotencyConflict as error:
            raise _problem(
                status=409,
                code="RO-CORE-INTENT-IDEMPOTENCY-CONFLICT",
                title="Intent command key was already used",
                detail="The idempotency key is bound to a different project, actor, or draft command.",
                remediation="Do not reuse command keys. Reload the project and issue a new key for a new command.",
            ) from error
        except RepositoryProblem as error:
            raise _problem(
                status=500,
                code="RO-CORE-INTENT-WRITE-FAILED",
                title="Research intent draft was not saved",
                detail="The local idempotency authority could not be validated.",
                remediation="The prior revision remains authoritative. Run project health checks before retrying.",
                retryable=True,
            ) from error
        if replay is not None:
            try:
                decoded = _decoded_records((replay,))[0]
            except IndexError as error:
                raise _problem(
                    status=500,
                    code="RO-CORE-INTENT-WRITE-FAILED",
                    title="Research intent draft was not saved",
                    detail="The committed idempotent result could not be validated.",
                    remediation="Keep the prior revision authoritative and run project health checks.",
                ) from error
            revisions = self._read(repository)
            self._read_workflow_authority(repository, revisions)
            return _projection(decoded)

        revisions = self._read(repository)
        existing_workflow_authority = self._read_workflow_authority(repository, revisions)
        current = _projection(revisions[0]) if revisions else None
        current_revision = current.revision if current is not None else 0
        if command.expected_revision != current_revision:
            raise _problem(
                status=409,
                code="RO-CORE-INTENT-REVISION-CONFLICT",
                title="Research intent changed",
                detail="The draft was based on an older local intent revision.",
                remediation="Reload, compare the current revision, and reapply the intended changes.",
            )
        preview = _impact(current, command.to_impact_request())
        if preview.acknowledgement_required:
            preview = _impact(
                current,
                command.to_impact_request(),
                stale_artifact_ids=self._stale_artifact_ids(stale_state_repository),
            )
        if preview.acknowledgement_required and command.impact_acknowledgement != preview.acknowledgement_token:
            raise _problem(
                status=409,
                code="RO-CORE-INTENT-IMPACT-ACK-REQUIRED",
                title="Intent change impact must be reviewed",
                detail="Corpus, novelty, or workflow scope changed without its exact current impact acknowledgement.",
                remediation=(
                    "Preview the affected workflows and outputs, acknowledge that preview, and retry the draft save."
                ),
            )
        if not preview.acknowledgement_required and command.impact_acknowledgement is not None:
            raise _problem(
                status=422,
                code="RO-CORE-INTENT-IMPACT-ACK-STALE",
                title="Intent impact acknowledgement is stale",
                detail="The supplied acknowledgement is not bound to a current scope change.",
                remediation="Clear the stale acknowledgement and preview again if scope changes.",
            )
        prior = revisions[0] if revisions else None
        domain_project_id = cast(str, prior["projectId"]) if prior is not None else new_uuid_v7()
        revision = _build_revision(
            command,
            prior=prior,
            domain_project_id=domain_project_id,
            actor_id=actor_id,
        )
        try:
            workflow_authority = _workflow_authority_mutation(
                existing_workflow_authority,
                prior_intent=prior,
                target_intent=revision,
                actor_id=actor_id,
            )
        except RepositoryProblem as error:
            raise _problem(
                status=500,
                code="RO-CORE-WORKFLOW-PROFILE-WRITE-FAILED",
                title="Workflow profile selection was not saved",
                detail="The intent-bound workflow selection or migration could not satisfy its governed contract.",
                remediation="The prior intent and workflow selection remain authoritative. Run project health checks.",
            ) from error
        content_json = _canonical_json(revision)
        digest = hashlib.sha256(content_json.encode("utf-8")).hexdigest()
        now = cast(str, revision["createdAt"])
        event = IntentAuditEvent(
            event_id=new_uuid_v7(),
            outbox_id=new_uuid_v7(),
            event_type="intent.draft.saved",
            occurred_at=now,
            trace_id=trace_id,
            actor_type="human",
            actor_id=actor_id,
            record_sha256=digest,
            command_sha256=command_sha256,
            idempotency_key=idempotency_key,
        )
        try:
            committed = repository.append(
                expected_revision=current_revision,
                domain_project_id=domain_project_id,
                manifest_project_id=manifest_project_id,
                record=IntentRevisionRecord(revision=current_revision + 1, content_json=content_json),
                event=event,
                workflow_authority=workflow_authority,
            )
        except RepositoryIdempotencyConflict as error:
            raise _problem(
                status=409,
                code="RO-CORE-INTENT-IDEMPOTENCY-CONFLICT",
                title="Intent command key was already used",
                detail="The idempotency key is bound to a different project, actor, or draft command.",
                remediation="Do not reuse command keys. Reload the project and issue a new key for a new command.",
            ) from error
        except RepositoryConflict as error:
            raise _problem(
                status=409,
                code="RO-CORE-INTENT-REVISION-CONFLICT",
                title="Research intent changed",
                detail="Another local command committed the next intent revision first.",
                remediation="Reload and compare the current revision before retrying.",
            ) from error
        except RepositoryProblem as error:
            raise _problem(
                status=500,
                code="RO-CORE-INTENT-WRITE-FAILED",
                title="Research intent draft was not saved",
                detail="The revision, provenance fact, and outbox event did not commit atomically.",
                remediation="The prior revision remains authoritative. Run project health checks and retry once.",
                retryable=True,
            ) from error
        emit_log_record(
            "intent.draft.saved",
            level="INFO",
            fields={"reasonCode": "intent-draft-saved", "traceId": trace_id},
        )
        self._read_workflow_authority(repository, (revision, *revisions))
        decoded = _decoded_records((committed,))[0]
        return _projection(decoded)


__all__ = ["IntentProblem", "ResearchIntentService"]
