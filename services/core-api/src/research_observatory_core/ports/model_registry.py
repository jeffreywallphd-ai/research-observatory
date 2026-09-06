"""Read-only host facts and current project-policy ports for model eligibility."""

from __future__ import annotations

from typing import Protocol

from ..model_gateway_contracts import ModelTaskSnapshot
from ..model_registry_contracts import (
    HostModelObservation,
    ModelCatalogRecord,
    ModelCatalogSummary,
    ModelManifest,
    RegistryPermission,
)


class ModelCatalogRepository(Protocol):
    def read(self, *, revision: int | None = None) -> ModelCatalogRecord | None: ...

    def history(self, *, before_revision: int | None = None, limit: int = 20) -> tuple[ModelCatalogSummary, ...]: ...

    def append(
        self,
        *,
        expected_revision: int,
        manifests: tuple[ModelManifest, ...],
        actor_id: str,
        idempotency_key: str,
        trace_id: str,
        occurred_at: str,
    ) -> ModelCatalogRecord: ...


class ModelInventory(Protocol):
    """Adapter facts, not renderer declarations or persisted readiness grants.

    Discovery contains provider-neutral metadata only. Observations must be
    revalidated for this service session and bind the exact manifest, including
    model/runtime/configuration/evaluation revisions. An adapter must not replay
    another session's observation after restart or after its underlying facts
    change. No model installation or evaluation provider is fabricated in W1.
    """

    def discover(self) -> tuple[ModelManifest, ...]: ...

    def observe(self) -> tuple[HostModelObservation, ...]: ...


class ModelEligibilityPolicy(Protocol):
    """Core-only fresh authority; callers cannot supply permission flags.

    Assess exact canonical input references and their current rights, the
    highest source classification, project restrictions, license applicability,
    deployment/egress approval and budget. Unknown authority returns denial.
    The result is explanatory matching evidence, not a dispatch permit. T03
    must reauthorize at execution, including any changed policy/rights facts.
    """

    def assess(
        self,
        *,
        project_id: str,
        catalog_revision: int,
        task: ModelTaskSnapshot,
        manifest: ModelManifest,
    ) -> RegistryPermission | None: ...


class EmptyModelInventory:
    def discover(self) -> tuple[ModelManifest, ...]:
        return ()

    def observe(self) -> tuple[HostModelObservation, ...]:
        return ()


class UnavailableModelEligibilityPolicy:
    def assess(
        self,
        *,
        project_id: str,
        catalog_revision: int,
        task: ModelTaskSnapshot,
        manifest: ModelManifest,
    ) -> RegistryPermission | None:
        return None
