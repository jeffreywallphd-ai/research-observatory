"""Canonical W1 identity/privacy checks, with explicit denial of missing authority."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

from .model_gateway_contracts import ModelTaskSnapshot, decode_model_task
from .model_registry_contracts import ModelManifest, RegistryPermission, canonical_hash
from .model_routing_contracts import input_references
from .models import PrivacyNetworkPolicy
from .ports.repositories import UnitOfWorkFactory
from .privacy import ProjectPrivacyService
from .projects import ProjectLifecycleService


class CanonicalModelEligibilityPolicy:
    """Current Core facts, not a renderer or manifest permission declaration.

    Coarse persisted rights do not prove model use. W1 has no canonical source
    classification or model-spending authority, so this adapter deliberately
    cannot grant positive execution. Later canonical resolvers must close those
    boundaries before a live provider can be enabled.
    """

    def __init__(
        self,
        *,
        projects: ProjectLifecycleService,
        privacy: ProjectPrivacyService,
        root: str,
        unit_of_work_factory: Callable[[Path, str], UnitOfWorkFactory],
        clock_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    ) -> None:
        self._projects = projects
        self._privacy = privacy
        self._root = root
        self._factory = unit_of_work_factory
        self._clock_ms = clock_ms

    def assess(
        self,
        *,
        project_id: str,
        catalog_revision: int,
        task: ModelTaskSnapshot,
        manifest: ModelManifest,
    ) -> RegistryPermission | None:
        owned = decode_model_task(task)
        if owned is None:
            return None
        manifest = ModelManifest.model_validate(manifest)

        def inspect(path: Path, canonical_project_id: str) -> RegistryPermission:
            if canonical_project_id != project_id:
                raise ValueError("canonical model project differs")
            privacy = self._privacy.get(self._root)
            if privacy.project_id != canonical_project_id:
                raise ValueError("canonical model privacy project differs")
            reasons = {
                "model-use-rights-unavailable",
                "source-classification-unavailable",
                "model-budget-authority-unavailable",
            }
            identities: list[dict[str, Any]] = []
            with self._factory(path, project_id)() as unit:
                for reference in input_references(owned):
                    revision = unit.aggregates.get_revision(reference["revisionId"])
                    current = unit.aggregates.get(reference["aggregateId"])
                    if (
                        revision.project_id != project_id
                        or revision.aggregate_id != reference["aggregateId"]
                        or revision.revision_id != reference["revisionId"]
                        or revision.object_sha256 is None
                        or "sha256:" + revision.object_sha256 != reference["contentHash"]
                    ):
                        reasons.add("canonical-input-identity-mismatch")
                    if revision.rights_status != "allowed" or current.rights_status != "allowed":
                        reasons.add("canonical-input-rights-denied")
                    unit.require_fresh_revision(revision.revision_id)
                    identities.append(
                        {
                            "aggregateId": revision.aggregate_id,
                            "revisionId": revision.revision_id,
                            "currentRevisionId": current.revision_id,
                            "rightsStatus": current.rights_status,
                            "contentHash": revision.object_sha256,
                        }
                    )
            if manifest.deployment != "local":
                reasons.add(
                    "model-egress-preview-required"
                    if privacy.network_policy is PrivacyNetworkPolicy.APPROVED_PROVIDERS
                    else "model-egress-denied"
                )
            requirements = cast(Mapping[str, Any], owned["requirements"])
            now = self._clock_ms()
            return RegistryPermission(
                project_id=project_id,
                catalog_revision=catalog_revision,
                task_hash=canonical_hash(owned),
                manifest_hash=canonical_hash(manifest),
                policy_revision=f"privacy-{privacy.revision}",
                rights_revision="canonical-inputs-" + canonical_hash(identities)[7:],
                observed_at_ms=now,
                expires_at_ms=now + 1000,
                # Echoing the requested class is not a classification grant:
                # source-classification-unavailable always denies this witness.
                data_class=requirements["dataClass"],
                required_modalities=("text",),
                permitted_deployments=(),
                maximum_cost_microunits=0,
                reason_codes=tuple(sorted(reasons)),
            )

        try:
            return self._projects.perform_open_project_action(root=self._root, require_write=True, action=inspect)
        except Exception:
            # Never expose project paths, repository errors or source metadata.
            return None
