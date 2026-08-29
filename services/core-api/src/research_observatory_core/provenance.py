"""Portable provenance construction and project-scoped lineage service."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

from .domain_contracts import is_uuid_v7, new_uuid_v7
from .ports.repositories import (
    AggregateRevision,
    AtomicRepositoryEvent,
    LineageDirection,
    LineagePage,
    ProvenanceLedgerRepository,
)
from .projects import ProjectLifecycleService
from .provenance_contracts import canonical_provenance_json, provenance_event_errors

_CONFIGURATION_DOCUMENT = b"research-observatory:canonical-aggregate-write:1.0.0"
_CONFIGURATION_HASH = f"sha256:{hashlib.sha256(_CONFIGURATION_DOCUMENT).hexdigest()}"
_ACTOR_TYPE = {"human": "human", "system": "system", "worker": "software", "model": "model"}


class ProvenanceProblem(RuntimeError):
    """Bounded provenance failure that does not disclose research content."""

    code = "RO-CORE-PROVENANCE-FAILED"


def _revision_hash(revision: AggregateRevision) -> str:
    document = {
        "aggregateId": revision.aggregate_id,
        "aggregateKind": revision.aggregate_kind,
        "contractVersion": revision.contract_version,
        "createdAt": revision.created_at,
        "displayLabelNormalized": revision.display_label_normalized,
        "displayLabelObserved": revision.display_label_observed,
        "knowledgeStatus": revision.knowledge_status,
        "modifiedAt": revision.modified_at,
        "objectSha256": revision.object_sha256,
        "projectId": revision.project_id,
        "revision": revision.revision,
        "revisionId": revision.revision_id,
        "rightsStatus": revision.rights_status,
    }
    payload = json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _entity(revision: AggregateRevision) -> dict[str, object]:
    return {
        "entityId": revision.aggregate_id,
        "revisionId": revision.revision_id,
        "entityKind": revision.aggregate_kind,
        "contentHash": _revision_hash(revision),
        "sensitivity": "private-research",
        "retentionClass": "project-lifetime",
    }


def _relation(
    relation_type: str,
    occurred_at: str,
    *,
    entity: AggregateRevision | None = None,
    related: AggregateRevision | None = None,
    activity_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, object]:
    return {
        "relationId": new_uuid_v7(),
        "relationType": relation_type,
        "entity": None if entity is None else {"entityId": entity.aggregate_id, "revisionId": entity.revision_id},
        "relatedEntity": None
        if related is None
        else {"entityId": related.aggregate_id, "revisionId": related.revision_id},
        "activityId": activity_id,
        "agentId": agent_id,
        "occurredAt": occurred_at,
    }


def canonical_aggregate_provenance_event(
    *,
    revision: AggregateRevision,
    previous: AggregateRevision | None,
    event: AtomicRepositoryEvent,
) -> str:
    """Construct the minimized v1 event required by one aggregate revision."""

    if event.actor_id is None or not is_uuid_v7(event.actor_id):
        raise ValueError("aggregate provenance requires an opaque UUIDv7 actor")
    if event.actor_type not in _ACTOR_TYPE:
        raise ValueError("aggregate provenance actor type is invalid")
    activity_id = new_uuid_v7()
    correlation_id = new_uuid_v7()
    output = _entity(revision)
    inputs = [] if previous is None else [_entity(previous)]
    relations = [
        _relation(
            "wasAssociatedWith",
            event.occurred_at,
            activity_id=activity_id,
            agent_id=event.actor_id,
        ),
        _relation("wasGeneratedBy", event.occurred_at, entity=revision, activity_id=activity_id),
        _relation("wasAttributedTo", event.occurred_at, entity=revision, agent_id=event.actor_id),
    ]
    if previous is not None:
        relations.extend(
            (
                _relation("used", event.occurred_at, entity=previous, activity_id=activity_id),
                _relation(
                    "wasDerivedFrom",
                    event.occurred_at,
                    entity=revision,
                    related=previous,
                    activity_id=activity_id,
                ),
            )
        )
    span_id = hashlib.sha256(event.outbox_id.encode("ascii")).hexdigest()[:16]
    record = {
        "specversion": "1.0",
        "id": event.event_id,
        "source": "urn:research-observatory:core",
        "type": f"org.research-observatory.{revision.aggregate_kind}.revision-recorded.v1",
        "subject": (
            f"project/{revision.project_id}/entity/{revision.aggregate_kind}/"
            f"{revision.aggregate_id}/revision/{revision.revision_id}"
        ),
        "time": event.occurred_at,
        "dataschema": "urn:research-observatory:schema:provenance-event:1.0.0",
        "datacontenttype": "application/json",
        "projectid": revision.project_id,
        "actorid": event.actor_id,
        "correlationid": correlation_id,
        "causationid": None,
        "traceparent": f"00-{event.trace_id}-{span_id}-01",
        "sensitivity": "private-research",
        "retentionclass": "project-lifetime",
        "schemaversion": "1.0.0",
        "data": {
            "agent": {
                "agentId": event.actor_id,
                "agentType": _ACTOR_TYPE[event.actor_type],
                "role": "canonical.writer",
            },
            "activity": {
                "activityId": activity_id,
                "activityType": f"{revision.aggregate_kind}.write",
                "status": "succeeded",
                "startedAt": event.occurred_at,
                "endedAt": event.occurred_at,
                "configuration": {
                    "configurationId": "core.aggregate-write",
                    "configurationVersion": "1.0.0",
                    "configurationHash": _CONFIGURATION_HASH,
                },
            },
            "inputs": inputs,
            "outputs": [output],
            "relations": relations,
            "payloadReference": {"state": "not-applicable"},
        },
    }
    errors = provenance_event_errors(record)
    if errors:
        raise ValueError("aggregate provenance contract failed: " + ", ".join(errors))
    return canonical_provenance_json(record)


RepositoryFactory = Callable[[Path, str], ProvenanceLedgerRepository]


class ProvenanceService:
    """Project-lifecycle-authorized, read-only provenance query boundary."""

    def __init__(
        self,
        projects: ProjectLifecycleService,
        repository_factory: RepositoryFactory | None,
    ) -> None:
        self._projects = projects
        self._repository_factory = repository_factory

    @classmethod
    def unavailable(cls, projects: ProjectLifecycleService) -> ProvenanceService:
        return cls(projects, None)

    def lineage(
        self,
        *,
        root: str,
        revision_id: str,
        direction: LineageDirection,
        cursor: int,
        page_size: int,
        max_depth: int,
    ) -> LineagePage:
        if self._repository_factory is None:
            raise ProvenanceProblem("provenance service is unavailable")
        if not is_uuid_v7(revision_id):
            raise ProvenanceProblem("lineage revision identity is invalid")
        if direction not in ("ancestors", "descendants"):
            raise ProvenanceProblem("lineage direction is invalid")
        if isinstance(cursor, bool) or not 0 <= cursor <= 10_000:
            raise ProvenanceProblem("lineage cursor is invalid")
        if isinstance(page_size, bool) or not 1 <= page_size <= 100:
            raise ProvenanceProblem("lineage page size is invalid")
        if isinstance(max_depth, bool) or not 1 <= max_depth <= 16:
            raise ProvenanceProblem("lineage depth is invalid")

        def query(path: Path, project_id: str) -> LineagePage:
            repository = cast(RepositoryFactory, self._repository_factory)(path, project_id)
            return repository.lineage(
                revision_id=revision_id,
                direction=direction,
                cursor=cursor,
                page_size=page_size,
                max_depth=max_depth,
            )

        return self._projects.perform_open_project_action(root=root, require_write=False, action=query)


__all__ = ["ProvenanceProblem", "ProvenanceService", "canonical_aggregate_provenance_event"]
