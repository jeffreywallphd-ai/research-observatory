"""Core-only project binding; no provider execution endpoint or caller grants."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol, TypeVar

from .domain_contracts import is_uuid_v7
from .model_registry_contracts import ModelRegistryCatalog
from .model_routing import ModelGateway
from .model_routing_contracts import CircuitState, RoutingEvent, RoutingPolicy, RoutingRun
from .model_routing_policy import CanonicalModelEligibilityPolicy
from .ports.model_gateway import ModelRoutingRepository
from .ports.model_registry import EmptyModelInventory, ModelCatalogRepository
from .ports.repositories import UnitOfWorkFactory
from .privacy import ProjectPrivacyService
from .projects import ProjectLifecycleService

_T = TypeVar("_T")


class _RoutingAction(Protocol):
    def __call__(self, operation: Callable[[ModelRoutingRepository], _T], *, write: bool = True) -> _T: ...


class _ProjectRoutingRepository:
    """Retaining a gateway never retains permission after close/lock/reopen."""

    def __init__(self, action: _RoutingAction) -> None:
        self._action = action

    def read(self, task_id: str) -> RoutingRun | None:
        return self._action(lambda repository: repository.read(task_id), write=False)

    @contextmanager
    def session(self) -> Iterator[None]:
        scope = self._action(lambda repository: repository.session())
        self._action(lambda _repository: scope.__enter__())
        try:
            yield
        finally:
            # Closing connection authority must remain possible after project lock.
            scope.__exit__(None, None, None)

    @contextmanager
    def atomic(self) -> Iterator[None]:
        scope = self._action(lambda repository: repository.atomic())
        with scope:
            yield

    def admit(self, run: RoutingRun) -> tuple[RoutingRun, bool]:
        return self._action(lambda repository: repository.admit(run))

    def append(self, task_id: str, *, expected_revision: int, event: RoutingEvent) -> RoutingRun:
        return self._action(
            lambda repository: repository.append(task_id, expected_revision=expected_revision, event=event)
        )

    def circuit(self, manifest_hash: str) -> CircuitState:
        return self._action(lambda repository: repository.circuit(manifest_hash), write=False)

    def change_circuit(
        self, state: CircuitState, *, expected_revision: int, expected_attempt_id: str | None = None
    ) -> CircuitState:
        return self._action(
            lambda repository: repository.change_circuit(
                state, expected_revision=expected_revision, expected_attempt_id=expected_attempt_id
            )
        )


class ProjectModelGatewayService:
    """Bind the existing protected project, canonical policy and Core principal.

    W1 production has no model adapters. Synthetic complete authority is supplied
    directly to ModelGateway in tests, never enabled by this composition.
    """

    def __init__(
        self,
        projects: ProjectLifecycleService,
        privacy: ProjectPrivacyService,
        *,
        local_actor_id: str | None = None,
        routing_repository_factory: Callable[[Path, str, str], ModelRoutingRepository] | None = None,
        catalog_repository_factory: Callable[[Path, str], ModelCatalogRepository] | None = None,
        unit_of_work_factory: Callable[[Path, str], UnitOfWorkFactory] | None = None,
    ) -> None:
        if local_actor_id is not None and not is_uuid_v7(local_actor_id):
            raise ValueError("model gateway actor must be a Core-owned UUIDv7")
        self._projects = projects
        self._privacy = privacy
        self._actor = local_actor_id
        self._routing_factory = routing_repository_factory
        self._catalog_factory = catalog_repository_factory
        self._unit_factory = unit_of_work_factory

    def for_project(self, root: str) -> tuple[ModelGateway, RoutingPolicy]:
        actor = self._actor
        routing_factory, catalog_factory, unit_factory = (
            self._routing_factory,
            self._catalog_factory,
            self._unit_factory,
        )
        if actor is None or routing_factory is None or catalog_factory is None or unit_factory is None:
            raise ValueError("model gateway Core authority is unavailable")

        def read_catalog(path: Path, identity: str) -> ModelRegistryCatalog:
            record = catalog_factory(path, identity).read()
            return (
                ModelRegistryCatalog(project_id=identity, revision=0, manifests=())
                if record is None
                else record.catalog
            )

        catalog, repository = self._projects.perform_open_project_action(
            root=root,
            require_write=True,
            action=lambda path, identity: (read_catalog(path, identity), routing_factory(path, identity, actor)),
        )

        def guarded(operation: Callable[[ModelRoutingRepository], _T], *, write: bool = True) -> _T:
            def perform(path: Path, identity: str) -> _T:
                if identity != catalog.project_id:
                    raise ValueError("model gateway project identity changed")
                return operation(repository)

            return self._projects.perform_open_project_action(root=root, require_write=write, action=perform)

        def current(expected: ModelRegistryCatalog) -> bool:
            return expected == self._projects.perform_open_project_action(
                root=root, require_write=True, action=read_catalog
            )

        return (
            ModelGateway(
                catalog=catalog,
                catalog_is_current=current,
                inventory=EmptyModelInventory(),
                authority=CanonicalModelEligibilityPolicy(
                    projects=self._projects, privacy=self._privacy, root=root, unit_of_work_factory=unit_factory
                ),
                adapters=(),
                repository=_ProjectRoutingRepository(guarded),
            ),
            RoutingPolicy(project_id=catalog.project_id, revision=1),
        )
