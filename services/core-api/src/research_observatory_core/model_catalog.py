"""Project-scoped model inventory inspection and trusted discovery snapshots."""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from .domain_contracts import is_uuid_v7
from .model_gateway_contracts import ModelTaskKind
from .model_registry_contracts import (
    HostModelObservation,
    ModelCatalogEntry,
    ModelCatalogProjection,
    ModelCatalogReadRequest,
    ModelCatalogRefreshRequest,
    ModelManifest,
    ModelRegistryCatalog,
    canonical_hash,
)
from .ports.model_registry import EmptyModelInventory, ModelCatalogRepository, ModelInventory
from .ports.repositories import RepositoryConflict, RepositoryProblem
from .projects import ProjectLifecycleService


class ModelCatalogProblem(RuntimeError):
    def __init__(self, code: str, title: str, *, status: int = 503) -> None:
        super().__init__(code)
        self.code = code
        self.title = title
        self.status = status


class ModelCatalogService:
    def __init__(
        self,
        projects: ProjectLifecycleService,
        *,
        repository_factory: Callable[[Path, str], ModelCatalogRepository] | None,
        local_actor_id: str | None,
        inventory: ModelInventory | None = None,
        clock_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    ) -> None:
        if local_actor_id is not None and not is_uuid_v7(local_actor_id):
            raise ValueError("model catalog actor must be a Core-owned UUIDv7")
        self._projects = projects
        self._repository_factory = repository_factory
        self._local_actor_id = local_actor_id
        self._inventory = inventory if inventory is not None else EmptyModelInventory()
        self._clock_ms = clock_ms

    @classmethod
    def unavailable(cls, projects: ProjectLifecycleService) -> ModelCatalogService:
        return cls(projects, repository_factory=None, local_actor_id=None)

    def _repo(self, path: Path, project_id: str) -> ModelCatalogRepository:
        if self._repository_factory is None:
            raise ModelCatalogProblem("RO-CORE-MODEL-CATALOG-UNAVAILABLE", "Model catalog is unavailable")
        return self._repository_factory(path, project_id)

    def get(self, command: ModelCatalogReadRequest) -> ModelCatalogProjection:
        try:
            return self._projects.perform_open_project_action(
                root=command.root,
                require_write=False,
                action=lambda path, project_id: self._project(self._repo(path, project_id), project_id, command),
            )
        except RepositoryProblem, OSError, ValueError, TypeError:
            raise ModelCatalogProblem("RO-CORE-MODEL-CATALOG-INVALID", "Model catalog could not be verified") from None

    def refresh(
        self,
        command: ModelCatalogRefreshRequest,
        *,
        idempotency_key: str,
        trace_id: str,
    ) -> ModelCatalogProjection:
        def update(path: Path, project_id: str) -> ModelCatalogProjection:
            if self._local_actor_id is None:
                raise ModelCatalogProblem(
                    "RO-CORE-MODEL-ACTOR-UNAVAILABLE", "Local model-change authority is unavailable"
                )
            # This is the only source of refreshed metadata. The request has no
            # manifest, actor, installed, qualified or policy-allow fields.
            manifests = self._inventory.discover()
            catalog = ModelRegistryCatalog(
                project_id=project_id, revision=command.expected_revision + 1, manifests=manifests
            )
            repository = self._repo(path, project_id)
            stored = repository.append(
                expected_revision=command.expected_revision,
                manifests=catalog.manifests,
                actor_id=self._local_actor_id,
                idempotency_key=idempotency_key,
                trace_id=trace_id,
                occurred_at=datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            )
            return self._project(
                repository, project_id, ModelCatalogReadRequest(root=command.root, revision=stored.revision)
            )

        try:
            return self._projects.perform_open_project_action(root=command.root, require_write=True, action=update)
        except RepositoryConflict:
            raise ModelCatalogProblem(
                "RO-CORE-MODEL-CATALOG-CONFLICT", "Model inventory changed; reload its current version", status=409
            ) from None
        except RepositoryProblem, OSError, ValueError, TypeError:
            raise ModelCatalogProblem(
                "RO-CORE-MODEL-CATALOG-FAILED", "Model inventory refresh did not complete"
            ) from None

    def _project(
        self,
        repository: ModelCatalogRepository,
        project_id: str,
        command: ModelCatalogReadRequest,
    ) -> ModelCatalogProjection:
        latest = repository.read()
        revision = 0 if latest is None else latest.revision
        selected = (
            latest
            if command.revision is None or command.revision == revision
            else repository.read(revision=command.revision)
        )
        if command.revision is not None and (selected is None or command.revision > revision):
            raise ModelCatalogProblem(
                "RO-CORE-MODEL-REVISION-NOT-FOUND", "Model inventory version was not found", status=404
            )
        catalog = (
            ModelRegistryCatalog(project_id=project_id, revision=0, manifests=())
            if selected is None
            else selected.catalog
        )
        observations: dict[str, list[HostModelObservation]] = defaultdict(list)
        inventory_state: Literal["not-configured", "available", "unavailable"] = (
            "not-configured" if isinstance(self._inventory, EmptyModelInventory) else "available"
        )
        try:
            values = self._inventory.observe()
            if not isinstance(values, tuple) or len(values) > 1000:
                raise ValueError("inventory observation bound is invalid")
            for value in values:
                observation = HostModelObservation.model_validate(value)
                observations[observation.manifest_hash].append(observation)
        except OSError, ValueError, TypeError, ValidationError:
            inventory_state = "unavailable"
            observations.clear()
        now = self._clock_ms()
        eligible_page = tuple(
            item for item in catalog.manifests if item.manifest_id > (command.after_manifest_id or "")
        )
        entries = tuple(
            self._entry(item, observations.get(canonical_hash(item), []), now) for item in eligible_page[:50]
        )
        history = repository.history(before_revision=min(command.before_history_revision or revision + 1, revision + 1))
        next_history = history[-1].revision if history and history[-1].revision > 1 else None
        return ModelCatalogProjection(
            project_id=project_id,
            revision=catalog.revision,
            latest_revision=revision,
            catalog_hash=None if selected is None else selected.catalog_hash,
            model_count=len(catalog.manifests),
            inventory_state=inventory_state,
            entries=entries,
            next_manifest_id=entries[-1].manifest.manifest_id if len(eligible_page) > 50 else None,
            history=history,
            next_history_revision=next_history,
        )

    @staticmethod
    def _entry(manifest: ModelManifest, observations: list[HostModelObservation], now: int) -> ModelCatalogEntry:
        availability: Literal["ready", "unavailable", "unknown", "stale"] = "unknown"
        reasons = ["task-policy-check-required"]
        qualified: tuple[ModelTaskKind, ...] = ()
        if len(observations) != 1:
            reasons.append("availability-unknown" if not observations else "observation-ambiguous")
        else:
            observation = observations[0]
            if not observation.observed_at_ms <= now < observation.expires_at_ms:
                availability = "stale"
                reasons.append("availability-stale")
            else:
                availability = observation.availability
                if observation.availability == "ready" and manifest.identity.evaluation_id is not None:
                    qualified = tuple(
                        kind for kind in observation.qualified_task_kinds if kind in manifest.capabilities
                    )
                if observation.availability != "ready":
                    reasons.append("runtime-unavailable")
        if not qualified:
            reasons.append("evaluation-unqualified")
        if manifest.retired:
            reasons.append("model-retired")
        return ModelCatalogEntry(
            manifest=manifest,
            manifest_hash=canonical_hash(manifest),
            availability=availability,
            qualified_task_kinds=qualified,
            reason_codes=tuple(sorted(reasons)),
        )
