"""Human-authoritative guided-workflow progress and Project Home projection."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from .domain_contracts import is_uuid_v7, new_uuid_v7
from .models import (
    WorkflowProgressCommand,
    WorkflowProgressProjection,
    WorkflowStageStateProjection,
    WorkflowStaleOutputProjection,
    WorkflowSupportingHandoffProjection,
)
from .ports.repositories import (
    DependencyImpactRepository,
    IntentRevisionRepository,
    RepositoryConflict,
    RepositoryIdempotencyConflict,
    RepositoryNotFound,
    RepositoryProblem,
    WorkflowProgressAuditEvent,
    WorkflowProgressCommandRecord,
    WorkflowProgressRepository,
    WorkflowStageStateRecord,
)
from .projects import ProjectLifecycleService
from .workflow_profile_contracts import (
    approved_workflow_profile_catalog,
    decode_project_workflow_selection,
    decode_workflow_stage_state,
)

_ProgressRepositoryFactory = Callable[[Path, str], WorkflowProgressRepository]
_IntentRepositoryFactory = Callable[[Path, str], IntentRevisionRepository]
_StaleRepositoryFactory = Callable[[Path, str], DependencyImpactRepository]
_CATALOG = approved_workflow_profile_catalog()
_PROFILES = {cast(str, item["profileId"]): item for item in cast(Sequence[Mapping[str, object]], _CATALOG["profiles"])}


@dataclass(slots=True)
class WorkflowProgressProblem(Exception):
    status: int
    code: str
    title: str
    detail: str
    remediation: str
    retryable: bool = False

    def __str__(self) -> str:
        return self.code


class _UnavailableProgressRepository:
    def read(self) -> tuple[WorkflowStageStateRecord, ...]:
        raise RepositoryProblem("workflow progress repository is unavailable")

    def resolve_completion_evidence(self, revision_ids: tuple[str, ...]) -> tuple[str, ...]:
        del revision_ids
        raise RepositoryProblem("workflow progress repository is unavailable")

    def replay(self, *, actor_id: str, idempotency_key: str, command_sha256: str) -> tuple[str, ...] | None:
        del actor_id, idempotency_key, command_sha256
        raise RepositoryProblem("workflow progress repository is unavailable")

    def append(self, **_kwargs: object) -> None:
        raise RepositoryProblem("workflow progress repository is unavailable")


class _UnavailableIntentRepository:
    def read_workflow_authority(self) -> object:
        raise RepositoryProblem("workflow selection repository is unavailable")


class _UnavailableStaleRepository:
    def stale_states(self, *, output_revision_id: str | None = None) -> object:
        del output_revision_id
        raise RepositoryProblem("workflow stale-state repository is unavailable")


def _problem(
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    remediation: str,
    retryable: bool = False,
) -> WorkflowProgressProblem:
    return WorkflowProgressProblem(status, code, title, detail, remediation, retryable)


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _canonical_json(value: object) -> str:
    def jsonable(item: object) -> object:
        if isinstance(item, Mapping):
            return {str(key): jsonable(nested) for key, nested in item.items()}
        if isinstance(item, tuple | list):
            return [jsonable(nested) for nested in item]
        return item

    return json.dumps(jsonable(value), ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _content_hash(value: Mapping[str, object]) -> str:
    without_hash = {key: item for key, item in value.items() if key != "revisionContentHash"}
    return "sha256:" + hashlib.sha256(_canonical_json(without_hash).encode("utf-8")).hexdigest()


def _selection_reference(selection: Mapping[str, object]) -> dict[str, object]:
    return {
        "selectionId": selection["selectionId"],
        "selectionRevisionId": selection["selectionRevisionId"],
        "revision": selection["revision"],
        "revisionContentHash": selection["revisionContentHash"],
    }


def _parent_reference(state: Mapping[str, object]) -> dict[str, object]:
    return {
        "stageStateId": state["stageStateId"],
        "stageStateRevisionId": state["stageStateRevisionId"],
        "revision": state["revision"],
        "revisionContentHash": state["revisionContentHash"],
    }


def _current_primary_reference(state: Mapping[str, object]) -> dict[str, object]:
    return {
        "stageStateId": state["stageStateId"],
        "stageStateRevisionId": state["stageStateRevisionId"],
        "revision": state["revision"],
        "revisionContentHash": state["revisionContentHash"],
        "projectId": state["projectId"],
        "selection": state["selection"],
        "profile": state["profile"],
        "stageKey": state["stageKey"],
        "pageContractId": state["pageContractId"],
        "passNumber": state["passNumber"],
        "status": "current",
    }


def _stage_state(
    selection: Mapping[str, object],
    *,
    actor_id: str,
    actor_type: Literal["human", "system"],
    stage: Mapping[str, object],
    status: str,
    pass_number: int = 1,
    parent: Mapping[str, object] | None = None,
    completion_evidence_ids: tuple[str, ...] = (),
    rationale: str | None = None,
    supporting_page_contract_id: str | None = None,
    current_primary: Mapping[str, object] | None = None,
    now: str,
) -> dict[str, object]:
    supporting = supporting_page_contract_id is not None
    stage_state_id = new_uuid_v7() if parent is None else cast(str, parent["stageStateId"])
    page_contract_id = supporting_page_contract_id or cast(str, stage["pageContractId"])
    state: dict[str, object] = {
        "schemaVersion": "1.0",
        "documentType": "research-observatory-workflow-stage-state",
        "contractVersion": "1.0.0",
        "stageStateId": stage_state_id,
        "stageStateRevisionId": new_uuid_v7(),
        "revision": 1 if parent is None else cast(int, parent["revision"]) + 1,
        "revisionContentHash": "sha256:" + "0" * 64,
        "projectId": selection["projectId"],
        "selection": _selection_reference(selection),
        "profile": selection["profile"],
        "stageKey": page_contract_id.removesuffix(".html") + "-1" if supporting else stage["stageKey"],
        "pageContractId": page_contract_id,
        "navigationRole": "supporting" if supporting else "primary",
        "passNumber": pass_number,
        "status": status,
        "completionEvidenceIds": list(completion_evidence_ids),
        "attention": (
            {
                "reasonCode": "researcher-blocked" if status == "blocked" else "researcher-attention",
                "rationale": rationale,
            }
            if status in {"attention-required", "blocked"}
            else None
        ),
        "staleCauses": [],
        "skipRationale": rationale if status == "skipped-with-rationale" else None,
        "supportReturn": {"currentPrimaryState": _current_primary_reference(current_primary)}
        if supporting and current_primary is not None
        else None,
        "parentState": _parent_reference(parent) if parent is not None else None,
        "updatedAt": now,
        "updatedBy": {"actorType": actor_type, "actorId": actor_id},
    }
    state["revisionContentHash"] = _content_hash(state)
    validation_current = current_primary if supporting else None
    if decode_workflow_stage_state(_CATALOG, selection, state, validation_current) is None:
        raise RepositoryProblem("workflow stage-state contract is invalid")
    return state


def _stage_projection(state: Mapping[str, object]) -> WorkflowStageStateProjection:
    parent = state.get("parentState")
    attention = state.get("attention")
    return WorkflowStageStateProjection(
        stage_state_id=cast(str, state["stageStateId"]),
        stage_state_revision_id=cast(str, state["stageStateRevisionId"]),
        revision=cast(int, state["revision"]),
        revision_content_hash=cast(str, state["revisionContentHash"]),
        parent_state_revision_id=cast(str, parent["stageStateRevisionId"]) if isinstance(parent, Mapping) else None,
        stage_key=cast(str, state["stageKey"]),
        page_contract_id=cast(str, state["pageContractId"]),
        navigation_role=cast(Any, state["navigationRole"]),
        pass_number=cast(int, state["passNumber"]),
        status=cast(Any, state["status"]),
        completion_evidence_ids=tuple(cast(Sequence[str], state["completionEvidenceIds"])),
        attention_reason=cast(str, attention["rationale"]) if isinstance(attention, Mapping) else None,
        stale_cause_ids=tuple(cast(Sequence[str], state["staleCauses"])),
        skip_rationale=state["skipRationale"] if isinstance(state["skipRationale"], str) else None,
        updated_at=cast(str, state["updatedAt"]),
    )


def _authority(
    intent_repository: IntentRevisionRepository,
) -> tuple[tuple[Mapping[str, object], ...], Mapping[str, object]]:
    authority = intent_repository.read_workflow_authority()
    selections: list[Mapping[str, object]] = []
    for record in authority.selections:
        try:
            candidate = json.loads(record.content_json)
        except json.JSONDecodeError, TypeError:
            raise RepositoryProblem("workflow selection JSON is invalid") from None
        decoded = decode_project_workflow_selection(_CATALOG, candidate)
        if decoded is None or decoded["revision"] != record.revision:
            raise RepositoryProblem("workflow selection authority is invalid")
        selection = cast(Mapping[str, object], decoded)
        if selection["revisionContentHash"] != _content_hash(selection):
            raise RepositoryProblem("workflow selection content hash differs")
        selections.append(selection)
    if not selections:
        raise RepositoryNotFound("workflow selection is unavailable")
    if [cast(int, item["revision"]) for item in selections] != list(range(1, len(selections) + 1)):
        raise RepositoryProblem("workflow selection history is discontinuous")
    return tuple(selections), selections[-1]


def _decoded_states(
    records: tuple[WorkflowStageStateRecord, ...],
    selections: tuple[Mapping[str, object], ...],
) -> tuple[Mapping[str, object], ...]:
    selection_by_revision_id = {cast(str, selection["selectionRevisionId"]): selection for selection in selections}
    decoded: list[Mapping[str, object]] = []
    by_revision_id: dict[str, Mapping[str, object]] = {}
    by_aggregate: dict[str, list[Mapping[str, object]]] = {}
    pending_support: list[tuple[Mapping[str, object], Mapping[str, object]]] = []
    for record in records:
        try:
            value = json.loads(record.content_json)
        except json.JSONDecodeError, TypeError:
            raise RepositoryProblem("workflow stage-state JSON is invalid") from None
        if not isinstance(value, dict) or not isinstance(value.get("selection"), dict):
            raise RepositoryProblem("workflow stage-state record is invalid")
        selection = selection_by_revision_id.get(cast(str, value["selection"].get("selectionRevisionId")))
        if selection is None or value.get("revisionContentHash") != _content_hash(value):
            raise RepositoryProblem("workflow stage-state authority differs")
        if value.get("navigationRole") == "supporting":
            pending_support.append((value, selection))
        elif decode_workflow_stage_state(_CATALOG, selection, value) is None:
            raise RepositoryProblem("workflow stage-state contract is invalid")
        state = cast(Mapping[str, object], value)
        revision_id = cast(str, state["stageStateRevisionId"])
        if revision_id in by_revision_id:
            raise RepositoryProblem("workflow stage-state revision identity is duplicated")
        by_revision_id[revision_id] = state
        by_aggregate.setdefault(cast(str, state["stageStateId"]), []).append(state)
        decoded.append(state)
    for states in by_aggregate.values():
        ordered = sorted(states, key=lambda item: cast(int, item["revision"]))
        if [cast(int, item["revision"]) for item in ordered] != list(range(1, len(ordered) + 1)):
            raise RepositoryProblem("workflow stage-state history is discontinuous")
        for index, state in enumerate(ordered):
            parent = state.get("parentState")
            if index == 0:
                if parent is not None:
                    raise RepositoryProblem("workflow stage-state predecessor is invalid")
                continue
            prior = ordered[index - 1]
            if _canonical_json(parent) != _canonical_json(_parent_reference(prior)):
                raise RepositoryProblem("workflow stage-state predecessor lookup differs")
    for state, selection in pending_support:
        support = cast(Mapping[str, object], state["supportReturn"])
        current_ref = cast(Mapping[str, object], support["currentPrimaryState"])
        current = by_revision_id.get(cast(str, current_ref["stageStateRevisionId"]))
        if current is None or decode_workflow_stage_state(_CATALOG, selection, state, current) is None:
            raise RepositoryProblem("workflow supporting-state return authority is invalid")
    return tuple(decoded)


def _heads(states: Sequence[Mapping[str, object]], selection_revision_id: str) -> tuple[Mapping[str, object], ...]:
    heads: dict[str, Mapping[str, object]] = {}
    for state in states:
        selection = cast(Mapping[str, object], state["selection"])
        if selection["selectionRevisionId"] != selection_revision_id:
            continue
        state_id = cast(str, state["stageStateId"])
        if state_id not in heads or cast(int, state["revision"]) > cast(int, heads[state_id]["revision"]):
            heads[state_id] = state
    return tuple(heads.values())


def _current_primary(heads: Sequence[Mapping[str, object]]) -> Mapping[str, object] | None:
    current = [state for state in heads if state["navigationRole"] == "primary" and state["status"] == "current"]
    if len(current) > 1:
        raise RepositoryProblem("workflow progress has multiple current primary heads")
    return current[0] if current else None


def _stale_projection(repository: DependencyImpactRepository) -> tuple[WorkflowStaleOutputProjection, ...]:
    results: list[WorkflowStaleOutputProjection] = []
    for state in repository.stale_states():
        authority = {
            "causeId": state.cause_id,
            "changeId": state.change_id,
            "confidence": state.confidence,
            "cycleGroupId": state.cycle_group_id,
            "depth": state.depth,
            "detectedAt": state.detected_at,
            "disposition": state.disposition,
            "outputRevisionId": state.output_revision_id,
            "pathLength": state.path_length,
            "pathRevisionIds": list(state.path_revision_ids),
            "pathTruncated": state.path_truncated,
            "propagationPolicyId": state.propagation_policy_id,
            "propagationPolicyVersion": state.propagation_policy_version,
            "reason": state.reason,
            "reviewRequired": state.review_required,
            "runId": state.run_id,
            "schemaVersion": "1.0",
        }
        results.append(
            WorkflowStaleOutputProjection(
                output_revision_id=state.output_revision_id,
                disposition=state.disposition,
                reason=state.reason,
                cause_reference_hash="sha256:" + hashlib.sha256(_canonical_json(authority).encode("utf-8")).hexdigest(),
                safest_next_action=(
                    "Review the exact dependency change before recomputing or accepting this output."
                    if state.disposition == "unknown-impact"
                    else "Review the stale cause and choose an approved selective recalculation."
                ),
            )
        )
    return tuple(results)


class WorkflowProgressService:
    """Project-scoped service that keeps scholarly stage authority human controlled."""

    def __init__(
        self,
        projects: ProjectLifecycleService,
        *,
        repository_factory: _ProgressRepositoryFactory,
        intent_repository_factory: _IntentRepositoryFactory,
        stale_state_repository_factory: _StaleRepositoryFactory,
        local_actor_id: str | None,
    ) -> None:
        if local_actor_id is not None and not is_uuid_v7(local_actor_id):
            raise ValueError("local workflow actor identity must be a UUIDv7")
        self._projects = projects
        self._repository_factory = repository_factory
        self._intent_repository_factory = intent_repository_factory
        self._stale_repository_factory = stale_state_repository_factory
        self._local_actor_id = local_actor_id

    @classmethod
    def unavailable(cls, projects: ProjectLifecycleService) -> WorkflowProgressService:
        return cls(
            projects,
            repository_factory=lambda _path, _project_id: cast(
                WorkflowProgressRepository, _UnavailableProgressRepository()
            ),
            intent_repository_factory=lambda _path, _project_id: cast(
                IntentRevisionRepository, _UnavailableIntentRepository()
            ),
            stale_state_repository_factory=lambda _path, _project_id: cast(
                DependencyImpactRepository, _UnavailableStaleRepository()
            ),
            local_actor_id=None,
        )

    def workspace(self, root: str) -> WorkflowProgressProjection:
        return self._projects.perform_open_project_action(
            root=root,
            require_write=False,
            action=lambda path, project_id: self._workspace(
                self._repository_factory(path, project_id),
                self._intent_repository_factory(path, project_id),
                self._stale_repository_factory(path, project_id),
                project_id,
            ),
        )

    def command(
        self,
        command: WorkflowProgressCommand,
        *,
        trace_id: str,
        idempotency_key: str,
    ) -> WorkflowProgressProjection:
        actor_id = self._local_actor_id
        if actor_id is None:
            raise _problem(
                status=503,
                code="RO-CORE-WORKFLOW-PROGRESS-ACTOR-UNAVAILABLE",
                title="Workflow progress authority is unavailable",
                detail="The current local researcher identity could not be validated.",
                remediation="Restore the local profile vault and retry the explicit stage action.",
                retryable=True,
            )
        return self._projects.perform_open_project_action(
            root=command.root,
            require_write=True,
            action=lambda path, project_id: self._command(
                self._repository_factory(path, project_id),
                self._intent_repository_factory(path, project_id),
                self._stale_repository_factory(path, project_id),
                project_id,
                command,
                trace_id=trace_id,
                idempotency_key=idempotency_key,
                actor_id=actor_id,
            ),
        )

    def _workspace(
        self,
        repository: WorkflowProgressRepository,
        intent_repository: IntentRevisionRepository,
        stale_repository: DependencyImpactRepository,
        project_id: str,
    ) -> WorkflowProgressProjection:
        try:
            selections, selection = _authority(intent_repository)
            states = _decoded_states(repository.read(), selections)
            return self._projection(selection, states, stale_repository, project_id)
        except RepositoryNotFound as error:
            raise _problem(
                status=409,
                code="RO-CORE-WORKFLOW-PROGRESS-SELECTION-REQUIRED",
                title="Guided workflow is unavailable",
                detail="This project has no current governed workflow selection.",
                remediation="Save a Research Intent with a primary use case, then retry.",
            ) from error
        except RepositoryProblem as error:
            raise _problem(
                status=500,
                code="RO-CORE-WORKFLOW-PROGRESS-READ-FAILED",
                title="Workflow progress is unavailable",
                detail="The immutable workflow progress history could not be validated.",
                remediation="Keep stage actions stopped and run project health checks before retrying.",
                retryable=True,
            ) from error

    def _projection(
        self,
        selection: Mapping[str, object],
        states: tuple[Mapping[str, object], ...],
        stale_repository: DependencyImpactRepository,
        project_id: str,
    ) -> WorkflowProgressProjection:
        profile_id = cast(str, cast(Mapping[str, object], selection["profile"])["profileId"])
        profile = _PROFILES[profile_id]
        stages = cast(Sequence[Mapping[str, object]], profile["stages"])
        selection_revision_id = cast(str, selection["selectionRevisionId"])
        heads = _heads(states, selection_revision_id)
        current = _current_primary(heads)
        primary_heads = [state for state in heads if state["navigationRole"] == "primary"]
        if current is None:
            completed_keys = {
                cast(str, state["stageKey"])
                for state in primary_heads
                if state["status"] in {"completed", "skipped-with-rationale"}
            }
            recommended = next(
                (stage for stage in stages if stage["stageKey"] not in completed_keys),
                stages[-1],
            )
        else:
            recommended = next(stage for stage in stages if stage["stageKey"] == current["stageKey"])
        supporting = sorted(
            (state for state in heads if state["navigationRole"] == "supporting"),
            key=lambda state: cast(str, state["updatedAt"]),
            reverse=True,
        )
        valid_support: Mapping[str, object] | None = None
        if current is not None:
            current_ref = _current_primary_reference(current)
            for state in supporting:
                support = cast(Mapping[str, object], state["supportReturn"])
                if _canonical_json(support["currentPrimaryState"]) == _canonical_json(current_ref):
                    valid_support = state
                    break
        checkpoint = cast(Mapping[str, object], recommended["checkpoint"])
        history_states = [
            state
            for state in reversed(states)
            if cast(Mapping[str, object], state["selection"])["selectionRevisionId"] == selection_revision_id
            and (current is None or state["stageStateRevisionId"] != current["stageStateRevisionId"])
        ][:512]
        return WorkflowProgressProjection(
            project_id=project_id,
            selection_revision_id=selection_revision_id,
            selection_revision_content_hash=cast(str, selection["revisionContentHash"]),
            profile_id=cast(Any, profile_id),
            profile_title=cast(str, profile["title"]),
            process_form=cast(Any, profile["cyclePolicy"]),
            bootstrap_required=not primary_heads,
            current=_stage_projection(current) if current is not None else None,
            recommended_stage_key=cast(str, recommended["stageKey"]),
            recommended_page_contract_id=cast(str, recommended["pageContractId"]),
            recommended_action=(
                "Start the guided workflow at this researcher-controlled stage."
                if not primary_heads
                else "Continue the current stage; completion requires explicit human evidence."
                if current is not None
                else "Review the completed workflow history and choose an explicit revisitation if needed."
            ),
            checkpoint_state=cast(Any, checkpoint["state"]),
            checkpoint_rationale=cast(str, checkpoint["rationale"]),
            supporting_handoff=(
                WorkflowSupportingHandoffProjection(
                    stage_state_id=cast(str, valid_support["stageStateId"]),
                    stage_state_revision_id=cast(str, valid_support["stageStateRevisionId"]),
                    revision_content_hash=cast(str, valid_support["revisionContentHash"]),
                    page_contract_id=cast(str, valid_support["pageContractId"]),
                    return_stage_state_revision_id=cast(str, current["stageStateRevisionId"]),
                )
                if valid_support is not None and current is not None
                else None
            ),
            stale_outputs=_stale_projection(stale_repository),
            history=tuple(_stage_projection(state) for state in history_states),
        )

    def _command(
        self,
        repository: WorkflowProgressRepository,
        intent_repository: IntentRevisionRepository,
        stale_repository: DependencyImpactRepository,
        project_id: str,
        command: WorkflowProgressCommand,
        *,
        trace_id: str,
        idempotency_key: str,
        actor_id: str,
    ) -> WorkflowProgressProjection:
        command_hash = hashlib.sha256(
            _canonical_json(
                {
                    "actor": {"actorId": actor_id, "actorType": "human"},
                    "command": command.model_dump(mode="json", by_alias=True),
                    "manifestProjectId": project_id,
                    "operation": "workflow.progress.command",
                    "schemaVersion": "1.0",
                }
            ).encode("utf-8")
        ).hexdigest()
        try:
            replay = repository.replay(
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                command_sha256=command_hash,
            )
            selections, selection = _authority(intent_repository)
            if (
                command.expected_selection_revision_id != selection["selectionRevisionId"]
                or command.expected_selection_revision_content_hash != selection["revisionContentHash"]
            ):
                raise RepositoryConflict("workflow selection changed")
            states = _decoded_states(repository.read(), selections)
            if replay is not None:
                present = {cast(str, state["stageStateRevisionId"]) for state in states}
                if any(item not in present for item in replay):
                    raise RepositoryProblem("workflow progress replay result is unavailable")
                return self._projection(selection, states, stale_repository, project_id)
            profile_id = cast(str, cast(Mapping[str, object], selection["profile"])["profileId"])
            profile = _PROFILES[profile_id]
            stages = cast(Sequence[Mapping[str, object]], profile["stages"])
            selection_revision_id = selection["selectionRevisionId"]
            if not isinstance(selection_revision_id, str):
                raise RepositoryProblem("workflow selection identity is invalid")
            heads = _heads(states, selection_revision_id)
            current = _current_primary(heads)
            revisit_head = next(
                (
                    state
                    for state in heads
                    if state["navigationRole"] == "primary" and state["stageKey"] == command.stage_key
                ),
                None,
            )
            precondition_state = (
                current if current is not None else revisit_head if command.action == "revisit" else None
            )
            if precondition_state is None:
                if command.expected_stage_state_revision_id is not None:
                    raise RepositoryConflict("workflow current stage changed")
            elif (
                command.expected_stage_state_revision_id != precondition_state["stageStateRevisionId"]
                or command.expected_stage_state_revision_content_hash != precondition_state["revisionContentHash"]
            ):
                raise RepositoryConflict("workflow current stage changed")
            now = _timestamp()
            next_states: list[dict[str, object]] = []
            if command.action == "start":
                if current is not None or heads or command.stage_key != stages[0]["stageKey"]:
                    raise RepositoryConflict("workflow start authority changed")
                next_states.append(
                    _stage_state(
                        selection,
                        actor_id=actor_id,
                        actor_type="human",
                        stage=stages[0],
                        status="current",
                        now=now,
                    )
                )
            else:
                if command.action != "revisit" and (current is None or command.stage_key != current["stageKey"]):
                    raise RepositoryConflict("workflow current stage differs")
                if command.action == "revisit" and current is not None and command.stage_key != current["stageKey"]:
                    raise RepositoryConflict("complete the current stage before revisiting an earlier stage")
                stage = next(item for item in stages if item["stageKey"] == command.stage_key)
                if command.action == "complete":
                    assert current is not None
                    evidence_ids = repository.resolve_completion_evidence(command.completion_evidence_revision_ids)
                    next_states.append(
                        _stage_state(
                            selection,
                            actor_id=actor_id,
                            actor_type="human",
                            stage=stage,
                            status="completed",
                            pass_number=cast(int, current["passNumber"]),
                            parent=current,
                            completion_evidence_ids=evidence_ids,
                            now=now,
                        )
                    )
                    index = list(stages).index(stage)
                    if index + 1 < len(stages):
                        next_stage = stages[index + 1]
                        next_states.append(
                            _stage_state(
                                selection,
                                actor_id=actor_id,
                                actor_type="human",
                                stage=next_stage,
                                status="current",
                                now=now,
                            )
                        )
                elif command.action == "revisit":
                    if profile["cyclePolicy"] != "revisitable":
                        raise _problem(
                            status=409,
                            code="RO-CORE-WORKFLOW-PROGRESS-CYCLE-DENIED",
                            title="This workflow is linear",
                            detail="The governed workflow profile does not authorize an additional pass.",
                            remediation="Continue the recorded linear sequence or revise the Research Intent profile.",
                        )
                    prior_pass = current if current is not None else revisit_head
                    if prior_pass is None:
                        raise RepositoryConflict("workflow revisit target is unavailable")
                    next_states.append(
                        _stage_state(
                            selection,
                            actor_id=actor_id,
                            actor_type="human",
                            stage=stage,
                            status="current",
                            pass_number=cast(int, prior_pass["passNumber"]) + 1,
                            parent=prior_pass,
                            now=now,
                        )
                    )
                elif command.action == "open-supporting":
                    assert current is not None
                    next_states.append(
                        _stage_state(
                            selection,
                            actor_id=actor_id,
                            actor_type="human",
                            stage=stage,
                            status="in-progress",
                            pass_number=cast(int, current["passNumber"]),
                            supporting_page_contract_id=command.supporting_page_contract_id,
                            current_primary=current,
                            now=now,
                        )
                    )
                elif command.action in {"mark-attention", "block", "skip"}:
                    assert current is not None
                    if command.action == "skip" and stage["optional"] is not True:
                        raise RepositoryConflict("required workflow stage cannot be skipped")
                    status = {
                        "mark-attention": "attention-required",
                        "block": "blocked",
                        "skip": "skipped-with-rationale",
                    }[command.action]
                    next_states.append(
                        _stage_state(
                            selection,
                            actor_id=actor_id,
                            actor_type="human",
                            stage=stage,
                            status=status,
                            pass_number=cast(int, current["passNumber"]),
                            parent=current,
                            rationale=command.rationale,
                            now=now,
                        )
                    )
                else:
                    raise RepositoryProblem("workflow progress action is unsupported")
            record_json = tuple(_canonical_json(state) for state in next_states)
            result_ids = tuple(cast(str, state["stageStateRevisionId"]) for state in next_states)
            event_type = (
                "workflow.stage.supporting-opened"
                if command.action == "open-supporting"
                else "workflow.stage.progressed"
            )
            repository.append(
                expected_selection_revision_id=selection["selectionRevisionId"],
                expected_selection_revision_content_hash=selection["revisionContentHash"],
                expected_current_revision_id=(
                    cast(str, current["stageStateRevisionId"]) if current is not None else None
                ),
                expected_current_revision_content_hash=cast(str, current["revisionContentHash"])
                if current is not None
                else None,
                records=tuple(
                    WorkflowStageStateRecord(storage_revision=0, content_json=value) for value in record_json
                ),
                command=WorkflowProgressCommandRecord(
                    actor_id=actor_id,
                    idempotency_key=idempotency_key,
                    command_sha256=command_hash,
                    result_revision_ids=result_ids,
                ),
                event=WorkflowProgressAuditEvent(
                    event_id=new_uuid_v7(),
                    outbox_id=new_uuid_v7(),
                    event_type=event_type,
                    occurred_at=now,
                    trace_id=trace_id,
                    actor_type="human",
                    actor_id=actor_id,
                    record_sha256=hashlib.sha256(_canonical_json(list(record_json)).encode("utf-8")).hexdigest(),
                ),
            )
            refreshed = _decoded_states(repository.read(), selections)
            return self._projection(selection, refreshed, stale_repository, project_id)
        except WorkflowProgressProblem:
            raise
        except RepositoryIdempotencyConflict as error:
            raise _problem(
                status=409,
                code="RO-CORE-WORKFLOW-PROGRESS-IDEMPOTENCY-CONFLICT",
                title="Workflow action key is already bound",
                detail="This action key was previously used for different workflow authority.",
                remediation="Reload Project Home before issuing a distinct action.",
            ) from error
        except RepositoryConflict as error:
            raise _problem(
                status=409,
                code="RO-CORE-WORKFLOW-PROGRESS-CONFLICT",
                title="Workflow progress changed",
                detail="The stage action was based on stale project or stage authority.",
                remediation="Reload Project Home and review the current stage before retrying.",
            ) from error
        except RepositoryNotFound as error:
            raise _problem(
                status=422,
                code="RO-CORE-WORKFLOW-PROGRESS-EVIDENCE-NOT-FOUND",
                title="Completion evidence is unavailable",
                detail="One or more completion-evidence revisions are not canonical in this project.",
                remediation="Select exact project-owned evidence revisions and retry.",
            ) from error
        except RepositoryProblem as error:
            raise _problem(
                status=500,
                code="RO-CORE-WORKFLOW-PROGRESS-WRITE-FAILED",
                title="Workflow progress was not changed",
                detail="The stage transaction could not be validated or committed.",
                remediation="Keep the prior stage authoritative and retry after project health checks.",
                retryable=True,
            ) from error


__all__ = ["WorkflowProgressProblem", "WorkflowProgressService"]
