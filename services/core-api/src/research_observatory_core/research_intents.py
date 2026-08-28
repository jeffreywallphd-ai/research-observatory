"""Versioned Research Intent draft, impact-preview, and persistence authority."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

from .domain_contracts import is_uuid_v7, new_uuid_v7
from .logging import emit_log_record
from .models import (
    IntentDraftProjection,
    IntentDraftRequest,
    IntentImpactPreview,
    IntentImpactRequest,
    IntentRevisionSummary,
    IntentWorkspaceProjection,
)
from .ports.repositories import (
    IntentAuditEvent,
    IntentRevisionRecord,
    IntentRevisionRepository,
    RepositoryConflict,
    RepositoryIdempotencyConflict,
    RepositoryProblem,
)
from .projects import ProjectLifecycleService
from .research_intent_contracts import decode_research_intent_revision

_RepositoryFactory = Callable[[Path, str], IntentRevisionRepository]
_MAX_HISTORY = 100


class _UnavailableIntentRepository(IntentRevisionRepository):
    """Fail-closed composition used when no concrete local adapter is supplied."""

    def read(self) -> tuple[IntentRevisionRecord, ...]:
        raise RepositoryProblem("research intent repository is unavailable")

    def replay(
        self,
        *,
        manifest_project_id: str,
        actor_id: str,
        idempotency_key: str,
        command_sha256: str,
    ) -> IntentRevisionRecord | None:
        del manifest_project_id, actor_id, idempotency_key, command_sha256
        raise RepositoryProblem("research intent repository is unavailable")

    def append(
        self,
        *,
        expected_revision: int,
        domain_project_id: str,
        manifest_project_id: str,
        record: IntentRevisionRecord,
        event: IntentAuditEvent,
    ) -> IntentRevisionRecord:
        del expected_revision, domain_project_id, manifest_project_id, record, event
        raise RepositoryProblem("research intent repository is unavailable")


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
_WORKFLOWS = {
    "rapid-orientation": ("Search Studio", "Corpus Canvas", "Document Reader", "Claim Graph", "Synthesis Studio"),
    "systematic-review": (
        "Source Manager",
        "Search Studio",
        "Screening",
        "Evidence Matrix",
        "Synthesis Studio",
        "Audit & Lineage",
    ),
    "living-review": ("Living Monitor", "Search Studio", "Screening", "Evidence Matrix", "Synthesis Studio"),
    "theory-synthesis": (
        "Search Studio",
        "Evidence Matrix",
        "Theory Map",
        "Claim Graph",
        "Opportunity Radar",
        "Synthesis Studio",
    ),
    "hermeneutic-inquiry": ("Search Studio", "Document Reader", "Research Notebook", "Synthesis Studio"),
    "critical-problematization": (
        "Search Studio",
        "Research Notebook",
        "Evidence Matrix",
        "Critical Lens",
        "Claim Graph",
    ),
    "technical-landscape": ("Search Studio", "Corpus Canvas", "Screening", "Evidence Matrix", "Opportunity Radar"),
    "novelty-audit": ("Research Intent", "Search Studio", "Evidence Matrix", "Opportunity Radar", "Novelty Audit"),
    "empirical-study-design": ("Research Intent", "Opportunity Radar", "Study Design Studio", "Audit & Lineage"),
    "empirical-study-to-article": (
        "Study Design Studio",
        "Technical Reports",
        "Evidence Matrix",
        "Manuscript Blueprint",
        "Manuscript Studio",
    ),
    "empirical-results-to-article": (
        "Technical Reports",
        "Evidence Matrix",
        "Manuscript Blueprint",
        "Manuscript Studio",
    ),
    "theory-article-development": ("Theory Map", "Claim Graph", "Manuscript Blueprint", "Manuscript Studio"),
    "critical-article-development": ("Critical Lens", "Claim Graph", "Manuscript Blueprint", "Manuscript Studio"),
    "manuscript-review-revision": (
        "Reviewer Simulation",
        "Revision & Response",
        "Manuscript Studio",
        "Audit & Lineage",
    ),
}
_OUTPUTS = {
    "rapid-orientation": ("Orientation synthesis", "Field vocabulary", "Seminal-work reading list"),
    "systematic-review": ("Screening protocol", "Evidence matrix", "Review synthesis", "Audit trail"),
    "living-review": ("Monitoring plan", "Differential screening queue", "Updated synthesis"),
    "theory-synthesis": ("Theory map", "Claim graph", "Boundary-condition synthesis"),
    "hermeneutic-inquiry": ("Interpretive notebook", "Reframing history", "Interpretive synthesis"),
    "critical-problematization": ("Critical lens", "Stakeholder account", "Problematization dossier"),
    "technical-landscape": ("Benchmark comparison", "Technical evidence matrix", "Landscape synthesis"),
    "novelty-audit": ("Nearest-prior-work challenge", "Novelty dossier", "Bounded opportunity statement"),
    "empirical-study-design": ("Study protocol", "Validity review", "Analysis plan"),
    "empirical-study-to-article": ("Verified result set", "Manuscript blueprint", "Evidence-grounded manuscript"),
    "empirical-results-to-article": ("Result reconciliation", "Manuscript blueprint", "Evidence-grounded manuscript"),
    "theory-article-development": ("Theory article blueprint", "Claim-evidence plan", "Manuscript"),
    "critical-article-development": ("Critical article blueprint", "Reflexivity record", "Manuscript"),
    "manuscript-review-revision": ("Reviewer issue map", "Revision record", "Response letter"),
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


def _projection(revision: Mapping[str, object]) -> IntentDraftProjection:
    source = cast(Mapping[str, object], revision["sourceScope"])
    novelty = cast(Mapping[str, object], revision["noveltyStandard"])
    autonomy = cast(Mapping[str, object], revision["autonomy"])
    stopping = cast(Mapping[str, object], revision["stoppingRule"])
    unresolved = tuple(cast(Sequence[str], revision["unresolvedDecisions"]))
    temporal = cast(Mapping[str, object], source.get("temporalCoverage", {}))
    return IntentDraftProjection(
        intent_id=cast(str, revision["intentId"]),
        revision_id=cast(str, revision["revisionId"]),
        revision=cast(int, revision["revision"]),
        revision_content_hash=cast(str, revision["revisionContentHash"]),
        created_at=cast(str, revision["createdAt"]),
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
        can_request_acceptance=not unresolved,
        launch_ready=False,
    )


def _summary(revision: Mapping[str, object]) -> IntentRevisionSummary:
    unresolved = cast(Sequence[object], revision["unresolvedDecisions"])
    return IntentRevisionSummary(
        revision=cast(int, revision["revision"]),
        revision_id=cast(str, revision["revisionId"]),
        revision_content_hash=cast(str, revision["revisionContentHash"]),
        created_at=cast(str, revision["createdAt"]),
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


def _scope_from_projection(projection: IntentDraftProjection) -> dict[str, object]:
    return {
        "primaryUseCase": projection.primary_use_case,
        "sourceKinds": list(projection.source_kinds),
        "languageCodes": list(projection.language_codes),
        "startYear": projection.start_year,
        "endYear": projection.end_year,
        "includePrivateReports": projection.include_private_reports,
        "noveltyStandard": projection.novelty_standard,
    }


def _scope_from_request(command: IntentImpactRequest) -> dict[str, object]:
    return {
        "primaryUseCase": command.primary_use_case,
        "sourceKinds": list(command.source_kinds),
        "languageCodes": list(command.language_codes),
        "startYear": command.start_year,
        "endYear": command.end_year,
        "includePrivateReports": command.include_private_reports,
        "noveltyStandard": command.novelty_standard,
    }


def _impact(current: IntentDraftProjection | None, command: IntentImpactRequest) -> IntentImpactPreview:
    if current is None:
        return IntentImpactPreview(
            expected_revision=command.expected_revision,
            change_categories=(),
            affected_workflows=(),
            affected_outputs=(),
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
            warnings=(),
            acknowledgement_required=False,
            acknowledgement_token=None,
        )
    old_case = current.primary_use_case
    new_case = command.primary_use_case
    workflows = tuple(dict.fromkeys((*_WORKFLOWS[old_case], *_WORKFLOWS[new_case])))
    outputs = tuple(dict.fromkeys((*_OUTPUTS[old_case], *_OUTPUTS[new_case])))
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
        "baseRevisionContentHash": current.revision_content_hash,
        "categories": categories,
        "expectedRevision": command.expected_revision,
        "scope": after,
    }
    token = hashlib.sha256(_canonical_json(token_payload).encode("utf-8")).hexdigest()
    return IntentImpactPreview(
        expected_revision=command.expected_revision,
        change_categories=cast(Any, tuple(categories)),
        affected_workflows=workflows,
        affected_outputs=outputs,
        warnings=tuple(warnings),
        acknowledgement_required=True,
        acknowledgement_token=token,
    )


class ResearchIntentService:
    """Project-scoped application service for non-governing draft revisions."""

    def __init__(
        self,
        projects: ProjectLifecycleService,
        *,
        repository_factory: _RepositoryFactory,
        local_actor_id: str | None,
    ) -> None:
        if local_actor_id is not None and not is_uuid_v7(local_actor_id):
            raise ValueError("local actor identity must be a UUIDv7")
        self._projects = projects
        self._repository_factory = repository_factory
        self._local_actor_id = local_actor_id

    @classmethod
    def unavailable(cls, projects: ProjectLifecycleService) -> ResearchIntentService:
        return cls(
            projects,
            repository_factory=lambda _path, _project_id: _UnavailableIntentRepository(),
            local_actor_id=None,
        )

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
                self._repository_factory(path, project_id), project_id, command
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
                project_id,
                command,
                trace_id=trace_id,
                idempotency_key=idempotency_key,
                actor_id=actor_id,
            ),
        )

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

    def _workspace(
        self,
        repository: IntentRevisionRepository,
        project_id: str,
    ) -> IntentWorkspaceProjection:
        revisions = self._read(repository)
        return IntentWorkspaceProjection(
            project_id=project_id,
            current=_projection(revisions[0]) if revisions else None,
            history=tuple(_summary(revision) for revision in revisions[:_MAX_HISTORY]),
        )

    def _preview(
        self,
        repository: IntentRevisionRepository,
        _project_id: str,
        command: IntentImpactRequest,
    ) -> IntentImpactPreview:
        revisions = self._read(repository)
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
        return _impact(current, command)

    def _save(
        self,
        repository: IntentRevisionRepository,
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
            return _projection(decoded)

        revisions = self._read(repository)
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
        decoded = _decoded_records((committed,))[0]
        return _projection(decoded)


__all__ = ["IntentProblem", "ResearchIntentService"]
