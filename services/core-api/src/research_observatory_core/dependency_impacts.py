"""Deterministic material-dependency impact planning without persistence authority."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from heapq import heappop, heappush
from typing import Literal

from research_observatory_core.domain_contracts import is_uuid_v7
from research_observatory_core.ports.repositories import (
    DEFAULT_DEPENDENCY_IMPACT_LIMITS,
    AggregateKind,
    ConditionalDependencyDecision,
    DependencyChange,
    DependencyCycleGroup,
    DependencyImpactItem,
    DependencyImpactLimitExceeded,
    DependencyImpactLimits,
    DependencyImpactPreview,
    DependencyKind,
    DependencyRelationType,
    RepositoryConflict,
    RepositoryProblem,
)

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^(?!.*(?:\.\.|--))[a-z](?:[a-z0-9.-]{0,126}[a-z0-9])?$")
_ACTOR_IDENTIFIER = re.compile(r"^(?!.*(?:\.\.|--))[a-z](?:[a-z0-9.-]{0,198}[a-z0-9])?$")
_SEMVER = re.compile(r"^(?:0|[1-9][0-9]{0,8})\.(?:0|[1-9][0-9]{0,8})\.(?:0|[1-9][0-9]{0,8})$")
_REVISION_KINDS = frozenset({"source-revision", "evidence-record", "ontology-version", "human-decision"})
_CONFIGURATION_KINDS = frozenset(
    {"prompt-version", "model-version", "parameter-set", "schema-version", "template-version", "code-version"}
)


@dataclass(frozen=True, slots=True)
class DependencyGraphEdge:
    """Detached exact edge used by the bounded impact planner."""

    dependency_id: str
    input_revision_id: str | None
    output_revision_id: str
    output_kind: AggregateKind
    relation_type: DependencyRelationType
    fingerprint: str
    governing_policy_id: str
    governing_policy_version: str
    configuration_id: str | None = None
    configuration_version: str | None = None
    dependency_kind: DependencyKind = "source-revision"


def _canonical_sha256(document: object) -> str:
    payload = json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def validate_dependency_impact_limits(limits: DependencyImpactLimits) -> None:
    values = (
        ("max_nodes", limits.max_nodes, DEFAULT_DEPENDENCY_IMPACT_LIMITS.max_nodes),
        ("max_edges", limits.max_edges, DEFAULT_DEPENDENCY_IMPACT_LIMITS.max_edges),
        ("max_depth", limits.max_depth, DEFAULT_DEPENDENCY_IMPACT_LIMITS.max_depth),
        ("max_path_samples", limits.max_path_samples, DEFAULT_DEPENDENCY_IMPACT_LIMITS.max_path_samples),
        ("max_legacy_samples", limits.max_legacy_samples, DEFAULT_DEPENDENCY_IMPACT_LIMITS.max_legacy_samples),
    )
    if limits.max_path_samples < 2 or any(
        isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum
        for _, value, maximum in values
    ):
        raise ValueError("dependency impact limits must be positive integers within immutable maxima")


def _canonical_utc(value: str) -> bool:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", value) is None:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return False
    return parsed.isoformat(timespec="milliseconds").replace("+00:00", "Z") == value


def _canonical_actor(value: str) -> bool:
    return is_uuid_v7(value) or _ACTOR_IDENTIFIER.fullmatch(value) is not None


def _validate_change(change: DependencyChange) -> None:
    revision_change = change.previous_revision_id is not None or change.replacement_revision_id is not None
    configuration_change = (
        change.configuration_id is not None
        or change.previous_configuration_version is not None
        or change.replacement_configuration_version is not None
    )
    if (
        not is_uuid_v7(change.change_id)
        or not change.idempotency_key
        or len(change.idempotency_key) > 200
        or change.reason
        not in {
            "SOURCE_VERSION",
            "RIGHTS_POLICY",
            "SCHEMA_VERSION",
            "MODEL_OR_PROMPT",
            "ONTOLOGY_MAPPING",
            "HUMAN_DECISION",
        }
        or _SHA256.fullmatch(change.previous_fingerprint) is None
        or (change.replacement_fingerprint is not None and _SHA256.fullmatch(change.replacement_fingerprint) is None)
        or _IDENTIFIER.fullmatch(change.propagation_policy_id) is None
        or _SEMVER.fullmatch(change.propagation_policy_version) is None
        or not _canonical_actor(change.actor_id)
        or not re.fullmatch(r"[0-9a-f]{32}", change.trace_id)
        or not _canonical_utc(change.occurred_at)
        or revision_change == configuration_change
    ):
        raise ValueError("dependency change authority is invalid")
    if revision_change:
        if (
            change.dependency_kind not in _REVISION_KINDS
            or not is_uuid_v7(change.previous_revision_id)
            or not is_uuid_v7(change.replacement_revision_id)
            or change.previous_revision_id == change.replacement_revision_id
        ):
            raise ValueError("revision change authority is invalid")
    elif (
        change.dependency_kind not in _CONFIGURATION_KINDS
        or change.configuration_id is None
        or _IDENTIFIER.fullmatch(change.configuration_id) is None
        or change.previous_configuration_version is None
        or _SEMVER.fullmatch(change.previous_configuration_version) is None
        or change.replacement_configuration_version is None
        or _SEMVER.fullmatch(change.replacement_configuration_version) is None
        or change.previous_configuration_version == change.replacement_configuration_version
    ):
        raise ValueError("configuration change authority is invalid")


def _edge_document(edge: DependencyGraphEdge) -> dict[str, str | None]:
    return {
        "configurationId": edge.configuration_id,
        "configurationVersion": edge.configuration_version,
        "dependencyId": edge.dependency_id,
        "dependencyKind": edge.dependency_kind,
        "fingerprint": edge.fingerprint,
        "governingPolicyId": edge.governing_policy_id,
        "governingPolicyVersion": edge.governing_policy_version,
        "inputRevisionId": edge.input_revision_id,
        "outputKind": edge.output_kind,
        "outputRevisionId": edge.output_revision_id,
        "relationType": edge.relation_type,
    }


def dependency_change_authority_document(change: DependencyChange) -> dict[str, object]:
    """Return the exact normalized change authority bound by previews and runs."""

    return {
        "actorId": change.actor_id,
        "changeId": change.change_id,
        "configurationId": change.configuration_id,
        "dependencyKind": change.dependency_kind,
        "idempotencyKey": change.idempotency_key,
        "occurredAt": change.occurred_at,
        "previousConfigurationVersion": change.previous_configuration_version,
        "previousFingerprint": change.previous_fingerprint,
        "previousRevisionId": change.previous_revision_id,
        "propagationPolicyId": change.propagation_policy_id,
        "propagationPolicyVersion": change.propagation_policy_version,
        "reason": change.reason,
        "replacementConfigurationVersion": change.replacement_configuration_version,
        "replacementFingerprint": change.replacement_fingerprint,
        "replacementRevisionId": change.replacement_revision_id,
        "traceId": change.trace_id,
    }


def conditional_decision_authority_document(decision: ConditionalDependencyDecision) -> dict[str, object]:
    """Return one complete normalized conditional-decision authority record."""

    return {
        "actorId": decision.actor_id,
        "decidedAt": decision.decided_at,
        "decisionId": decision.decision_id,
        "dependencyId": decision.dependency_id,
        "disposition": decision.disposition,
        "governingPolicyId": decision.governing_policy_id,
        "governingPolicyVersion": decision.governing_policy_version,
    }


def _decision_map(
    decisions: tuple[ConditionalDependencyDecision, ...],
) -> dict[str, ConditionalDependencyDecision]:
    mapped: dict[str, ConditionalDependencyDecision] = {}
    decision_ids: set[str] = set()
    for decision in decisions:
        if (
            not is_uuid_v7(decision.dependency_id)
            or not is_uuid_v7(decision.decision_id)
            or decision.disposition not in {"propagate", "ignore"}
            or _IDENTIFIER.fullmatch(decision.governing_policy_id) is None
            or _SEMVER.fullmatch(decision.governing_policy_version) is None
            or not _canonical_actor(decision.actor_id)
            or not _canonical_utc(decision.decided_at)
            or decision.dependency_id in mapped
            or decision.decision_id in decision_ids
        ):
            raise ValueError("conditional dependency decision authority is invalid")
        mapped[decision.dependency_id] = decision
        decision_ids.add(decision.decision_id)
    return mapped


def _origin_matches(change: DependencyChange, edge: DependencyGraphEdge) -> bool:
    if change.dependency_kind != edge.dependency_kind:
        return False
    if change.previous_revision_id is not None:
        return edge.input_revision_id == change.previous_revision_id
    return (
        edge.input_revision_id is None
        and edge.configuration_id == change.configuration_id
        and edge.configuration_version == change.previous_configuration_version
    )


def _strongly_connected_groups(
    adjacency: dict[str, set[str]],
    nodes: set[str],
) -> tuple[DependencyCycleGroup, ...]:
    graph = {node: tuple(sorted(target for target in adjacency.get(node, set()) if target in nodes)) for node in nodes}
    reverse: dict[str, list[str]] = {node: [] for node in nodes}
    for source, outgoing in graph.items():
        for target in outgoing:
            reverse[target].append(source)
    for incoming in reverse.values():
        incoming.sort()

    visited: set[str] = set()
    finish_order: list[str] = []
    for root in sorted(nodes):
        if root in visited:
            continue
        visited.add(root)
        stack: list[tuple[str, int]] = [(root, 0)]
        while stack:
            node, next_index = stack[-1]
            outgoing = graph[node]
            if next_index >= len(outgoing):
                stack.pop()
                finish_order.append(node)
                continue
            target = outgoing[next_index]
            stack[-1] = (node, next_index + 1)
            if target not in visited:
                visited.add(target)
                stack.append((target, 0))

    assigned: set[str] = set()
    groups: list[DependencyCycleGroup] = []
    for root in reversed(finish_order):
        if root in assigned:
            continue
        assigned.add(root)
        members: list[str] = []
        stack = [(root, False)]
        while stack:
            node, _ = stack.pop()
            members.append(node)
            for source in reversed(reverse[node]):
                if source not in assigned:
                    assigned.add(source)
                    stack.append((source, False))
        ordered = tuple(sorted(members))
        if len(ordered) > 1 or (len(ordered) == 1 and ordered[0] in graph[ordered[0]]):
            groups.append(
                DependencyCycleGroup(
                    cycle_group_id=_canonical_sha256({"cycleMembers": ordered}),
                    member_revision_ids=ordered,
                )
            )
    return tuple(sorted(groups, key=lambda item: item.member_revision_ids))


def plan_dependency_impact(
    project_id: str,
    change: DependencyChange,
    edges: tuple[DependencyGraphEdge, ...],
    *,
    decisions: tuple[ConditionalDependencyDecision, ...] = (),
    legacy_unreported_output_ids: tuple[str, ...] = (),
    limits: DependencyImpactLimits = DEFAULT_DEPENDENCY_IMPACT_LIMITS,
) -> DependencyImpactPreview:
    """Plan one exact change against a bounded immutable edge snapshot."""

    if not project_id:
        raise ValueError("project identity is required")
    _validate_change(change)
    validate_dependency_impact_limits(limits)
    decision_by_edge = _decision_map(decisions)
    legacy = tuple(sorted(set(legacy_unreported_output_ids)))
    if len(edges) > limits.max_edges:
        raise DependencyImpactLimitExceeded("dependency impact edge limit exceeded")
    if len(legacy) > limits.max_nodes:
        raise DependencyImpactLimitExceeded("dependency impact legacy-state limit exceeded")
    if any(not is_uuid_v7(output_revision_id) for output_revision_id in legacy):
        raise RepositoryProblem("dependency impact legacy state contains invalid authority")
    ordered_edges = tuple(sorted(edges, key=lambda item: item.dependency_id))
    if len({edge.dependency_id for edge in ordered_edges}) != len(ordered_edges):
        raise RepositoryProblem("dependency impact graph contains duplicate edge identity")
    edges_by_input: dict[str, list[DependencyGraphEdge]] = {}
    edge_by_id: dict[str, DependencyGraphEdge] = {}
    for edge in ordered_edges:
        revision_endpoint = edge.input_revision_id is not None
        configuration_endpoint = edge.configuration_id is not None or edge.configuration_version is not None
        if (
            not is_uuid_v7(edge.dependency_id)
            or not is_uuid_v7(edge.output_revision_id)
            or (edge.input_revision_id is not None and not is_uuid_v7(edge.input_revision_id))
            or edge.relation_type not in {"direct", "conditional", "non-material"}
            or edge.dependency_kind not in _REVISION_KINDS | _CONFIGURATION_KINDS
            or _SHA256.fullmatch(edge.fingerprint) is None
            or _IDENTIFIER.fullmatch(edge.governing_policy_id) is None
            or _SEMVER.fullmatch(edge.governing_policy_version) is None
            or revision_endpoint == configuration_endpoint
            or (
                configuration_endpoint
                and (
                    edge.configuration_id is None
                    or _IDENTIFIER.fullmatch(edge.configuration_id) is None
                    or edge.configuration_version is None
                    or _SEMVER.fullmatch(edge.configuration_version) is None
                )
            )
        ):
            raise RepositoryProblem("dependency impact graph contains invalid authority")
        edge_by_id[edge.dependency_id] = edge
        if edge.input_revision_id is not None:
            edges_by_input.setdefault(edge.input_revision_id, []).append(edge)
    if any(
        decision_dependency_id not in edge_by_id or edge_by_id[decision_dependency_id].relation_type != "conditional"
        for decision_dependency_id in decision_by_edge
    ):
        raise RepositoryConflict("conditional dependency decision does not govern a conditional graph edge")

    graph_sha256 = _canonical_sha256(
        {
            "edges": [_edge_document(edge) for edge in ordered_edges],
            "legacyUnreported": legacy,
            "projectId": project_id,
        }
    )
    impacts: dict[str, DependencyImpactItem] = {}
    adjacency: dict[str, set[str]] = {}
    processed_edges: set[str] = set()
    used_decisions: set[str] = set()
    expanded_rank: dict[str, int] = {}
    frontier: list[tuple[int, tuple[str, ...], str, DependencyGraphEdge, Literal["confirmed", "unknown"]]] = []
    replacement_changed = change.replacement_fingerprint is None or (
        change.replacement_fingerprint != change.previous_fingerprint
    )
    for edge in ordered_edges:
        if not _origin_matches(change, edge):
            continue
        if edge.fingerprint != change.previous_fingerprint:
            raise RepositoryConflict("dependency change fingerprint does not match the recorded edge")
        if replacement_changed:
            path: tuple[str, ...] = (
                (change.previous_revision_id, edge.output_revision_id)
                if change.previous_revision_id is not None
                else (edge.output_revision_id,)
            )
            heappush(
                frontier,
                (
                    1,
                    path,
                    edge.dependency_id,
                    edge,
                    "unknown" if change.replacement_fingerprint is None else "confirmed",
                ),
            )

    while frontier:
        depth, path, _, edge, inherited_confidence = heappop(frontier)
        if depth > limits.max_depth:
            raise DependencyImpactLimitExceeded("dependency impact depth limit exceeded")
        processed_edges.add(edge.dependency_id)
        if len(processed_edges) > limits.max_edges:
            raise DependencyImpactLimitExceeded("dependency impact edge limit exceeded")
        decision = decision_by_edge.get(edge.dependency_id)
        disposition: Literal["stale", "unknown-impact", "informational"]
        confidence: Literal["confirmed", "conditional", "unknown"]
        review_required = False
        propagate = False
        if edge.relation_type == "non-material":
            disposition = "informational"
            confidence = "confirmed"
        elif edge.relation_type == "conditional":
            if decision is None:
                disposition = "unknown-impact"
                confidence = "unknown"
                review_required = True
                propagate = True
            else:
                used_decisions.add(edge.dependency_id)
                if (
                    decision.governing_policy_id != edge.governing_policy_id
                    or decision.governing_policy_version != edge.governing_policy_version
                ):
                    raise RepositoryConflict("conditional dependency policy authority was substituted")
                if decision.disposition == "ignore":
                    disposition = "informational"
                    confidence = "conditional"
                else:
                    disposition = "unknown-impact" if inherited_confidence == "unknown" else "stale"
                    confidence = "unknown" if inherited_confidence == "unknown" else "conditional"
                    review_required = True
                    propagate = True
        else:
            disposition = "unknown-impact" if inherited_confidence == "unknown" else "stale"
            confidence = inherited_confidence
            propagate = True

        path_length = len(path)
        path_truncated = path_length > limits.max_path_samples
        sampled_path = (*path[: limits.max_path_samples - 1], path[-1]) if path_truncated else path
        candidate = DependencyImpactItem(
            output_revision_id=edge.output_revision_id,
            output_kind=edge.output_kind,
            disposition=disposition,
            depth=depth,
            relation_type=edge.relation_type,
            path_revision_ids=sampled_path,
            path_length=path_length,
            path_truncated=path_truncated,
            cycle_group_id=None,
            confidence=confidence,
            review_required=review_required,
        )
        previous = impacts.get(edge.output_revision_id)
        rank = {"informational": 0, "unknown-impact": 1, "stale": 2}
        if (
            previous is None
            or rank[candidate.disposition] > rank[previous.disposition]
            or (
                rank[candidate.disposition] == rank[previous.disposition]
                and (candidate.depth, candidate.path_revision_ids) < (previous.depth, previous.path_revision_ids)
            )
        ):
            impacts[edge.output_revision_id] = candidate
        if len(impacts) > limits.max_nodes:
            raise DependencyImpactLimitExceeded("dependency impact node limit exceeded")
        if not propagate:
            continue
        if edge.input_revision_id is not None:
            adjacency.setdefault(edge.input_revision_id, set()).add(edge.output_revision_id)
        propagation_rank = 2 if disposition == "stale" else 1
        if expanded_rank.get(edge.output_revision_id, 0) >= propagation_rank:
            continue
        expanded_rank[edge.output_revision_id] = propagation_rank
        downstream_confidence: Literal["confirmed", "unknown"] = (
            "unknown" if disposition == "unknown-impact" else "confirmed"
        )
        for downstream in edges_by_input.get(edge.output_revision_id, ()):
            next_path = (*path, downstream.output_revision_id)
            heappush(
                frontier,
                (depth + 1, next_path, downstream.dependency_id, downstream, downstream_confidence),
            )

    if used_decisions != set(decision_by_edge):
        raise RepositoryConflict("conditional dependency decision does not govern a reachable edge")
    cycle_groups = _strongly_connected_groups(adjacency, set(impacts))
    cycle_by_member = {member: group.cycle_group_id for group in cycle_groups for member in group.member_revision_ids}
    ordered_impacts = tuple(
        sorted(
            (replace(item, cycle_group_id=cycle_by_member.get(item.output_revision_id)) for item in impacts.values()),
            key=lambda item: (item.depth, item.output_revision_id, item.disposition),
        )
    )
    preview_body = {
        "change": dependency_change_authority_document(change),
        "cycleGroups": [
            {"cycleGroupId": group.cycle_group_id, "memberRevisionIds": group.member_revision_ids}
            for group in cycle_groups
        ],
        "graphSha256": graph_sha256,
        "decisions": [
            conditional_decision_authority_document(decision_by_edge[dependency_id])
            for dependency_id in sorted(decision_by_edge)
        ],
        "impacts": [
            {
                "confidence": item.confidence,
                "cycleGroupId": item.cycle_group_id,
                "depth": item.depth,
                "disposition": item.disposition,
                "outputKind": item.output_kind,
                "outputRevisionId": item.output_revision_id,
                "pathLength": item.path_length,
                "pathRevisionIds": item.path_revision_ids,
                "pathTruncated": item.path_truncated,
                "relationType": item.relation_type,
                "reviewRequired": item.review_required,
            }
            for item in ordered_impacts
        ],
        "legacyUnreportedCount": len(legacy),
        "legacyUnreportedSamples": legacy[: limits.max_legacy_samples],
        "projectId": project_id,
        "limits": {
            "maxDepth": limits.max_depth,
            "maxEdges": limits.max_edges,
            "maxLegacySamples": limits.max_legacy_samples,
            "maxNodes": limits.max_nodes,
            "maxPathSamples": limits.max_path_samples,
        },
        "visitedEdges": len(processed_edges),
        "visitedNodes": len(impacts),
    }
    return DependencyImpactPreview(
        project_id=project_id,
        change_id=change.change_id,
        graph_sha256=graph_sha256,
        preview_sha256=_canonical_sha256(preview_body),
        impacts=ordered_impacts,
        cycle_groups=cycle_groups,
        legacy_unreported_count=len(legacy),
        legacy_unreported_samples=legacy[: limits.max_legacy_samples],
        visited_nodes=len(impacts),
        visited_edges=len(processed_edges),
    )


__all__ = [
    "DependencyGraphEdge",
    "conditional_decision_authority_document",
    "dependency_change_authority_document",
    "plan_dependency_impact",
    "validate_dependency_impact_limits",
]
