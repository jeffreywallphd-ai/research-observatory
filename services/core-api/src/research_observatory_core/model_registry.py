"""Fail-closed model capability discovery; no provider dispatch or model I/O."""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable, Mapping
from typing import Any, cast

from pydantic import ValidationError

from .model_gateway_contracts import ModelTaskSnapshot, decode_model_task
from .model_registry_contracts import (
    HostModelObservation,
    ModelEligibilityCandidate,
    ModelManifest,
    ModelRegistryCatalog,
    ModelRegistryRejection,
    ModelRegistryResolution,
    RegistryPermission,
    canonical_hash,
)
from .ports.model_registry import ModelEligibilityPolicy, ModelInventory, UnavailableModelEligibilityPolicy

_QUALITY_ORDER = {"quality": 0, "balanced": 1, "economy": 2, "unrated": 3}


class ModelRegistry:
    def __init__(
        self,
        inventory: ModelInventory,
        policy: ModelEligibilityPolicy | None = None,
        *,
        clock_ms: Callable[[], int] = lambda: time.time_ns() // 1_000_000,
    ) -> None:
        self._inventory = inventory
        self._policy = policy if policy is not None else UnavailableModelEligibilityPolicy()
        self._clock_ms = clock_ms

    def resolve(self, catalog: ModelRegistryCatalog, task_value: object) -> ModelRegistryResolution:
        catalog = ModelRegistryCatalog.model_validate(catalog)
        task = decode_model_task(task_value)
        if task is None:
            return ModelRegistryResolution(
                project_id=catalog.project_id,
                catalog_revision=catalog.revision,
                task_hash=None,
                eligible=(),
                rejected=(),
                reason_codes=("model-task-invalid",),
            )
        task_hash = canonical_hash(task)
        now = self._clock_ms()
        by_hash: dict[str, list[HostModelObservation]] = defaultdict(list)
        try:
            observed = self._inventory.observe()
            if not isinstance(observed, tuple) or len(observed) > 1000:
                raise ValueError("invalid inventory bound")
            for reported_observation in observed:
                checked = HostModelObservation.model_validate(reported_observation)
                by_hash[checked.manifest_hash].append(checked)
        except OSError, ValueError, TypeError:
            by_hash.clear()
        eligible: list[tuple[ModelManifest, ModelEligibilityCandidate]] = []
        rejected: list[ModelRegistryRejection] = []
        for manifest in catalog.manifests:
            digest = canonical_hash(manifest)
            reasons: set[str] = set()
            observations = by_hash[digest]
            observation = observations[0] if len(observations) == 1 else None
            if not observations:
                reasons.add("availability-unknown")
            elif len(observations) != 1:
                reasons.add("observation-ambiguous")
            permission = self._permission(catalog, task, manifest)
            if permission is None:
                reasons.add("permission-unavailable")
            else:
                if (
                    permission.project_id,
                    permission.catalog_revision,
                    permission.task_hash,
                    permission.manifest_hash,
                ) != (
                    catalog.project_id,
                    catalog.revision,
                    task_hash,
                    digest,
                ):
                    reasons.add("permission-identity-mismatch")
                if not permission.observed_at_ms <= now < permission.expires_at_ms:
                    reasons.add("permission-stale")
                reasons.update(permission.reason_codes)
            reasons.update(self._rejections(manifest, task, observation, permission, now))
            if reasons:
                rejected.append(
                    ModelRegistryRejection(
                        manifest_id=manifest.manifest_id,
                        manifest_revision=manifest.revision,
                        manifest_hash=digest,
                        reason_codes=tuple(sorted(reasons)),
                    )
                )
            else:
                assert observation is not None and permission is not None
                eligible.append(
                    (
                        manifest,
                        ModelEligibilityCandidate(
                            manifest_id=manifest.manifest_id,
                            manifest_revision=manifest.revision,
                            manifest_hash=digest,
                            policy_revision=permission.policy_revision,
                            rights_revision=permission.rights_revision,
                            observation_expires_at_ms=min(observation.expires_at_ms, permission.expires_at_ms),
                        ),
                    )
                )
        eligible.sort(
            key=lambda entry: (
                _QUALITY_ORDER[entry[0].quality_tier],
                entry[0].cost_microunits_per_thousand_tokens
                if entry[0].cost_microunits_per_thousand_tokens is not None
                else 10**13,
                entry[0].manifest_id,
            )
        )
        return ModelRegistryResolution(
            project_id=catalog.project_id,
            catalog_revision=catalog.revision,
            task_hash=task_hash,
            eligible=tuple(item for _manifest, item in eligible),
            rejected=tuple(rejected),
            reason_codes=() if eligible else ("no-eligible-model",),
        )

    def _permission(
        self,
        catalog: ModelRegistryCatalog,
        task: ModelTaskSnapshot,
        manifest: ModelManifest,
    ) -> RegistryPermission | None:
        try:
            result = self._policy.assess(
                project_id=catalog.project_id,
                catalog_revision=catalog.revision,
                task=task,
                manifest=manifest,
            )
            return None if result is None else RegistryPermission.model_validate(result)
        except OSError, ValueError, TypeError, ValidationError:
            return None

    @staticmethod
    def _rejections(
        manifest: ModelManifest,
        task: ModelTaskSnapshot,
        observation: HostModelObservation | None,
        permission: RegistryPermission | None,
        now: int,
    ) -> set[str]:
        reasons: set[str] = set()
        requirements = cast(Mapping[str, Any], task["requirements"])
        pin = cast(Mapping[str, Any], task["execution"])
        if manifest.retired:
            reasons.add("model-retired")
        if task["taskKind"] not in manifest.capabilities:
            reasons.add("task-kind-unsupported")
        if not set(requirements["requiredFeatures"]).issubset(manifest.features):
            reasons.add("required-feature-unsupported")
        if requirements["maxInputTokens"] + requirements["maxOutputTokens"] > manifest.context_tokens:
            reasons.add("context-limit")
        if requirements["maxOutputTokens"] > manifest.max_output_tokens:
            reasons.add("output-limit")
        if requirements["citationRequirement"] == "required" and not manifest.supports_citations:
            reasons.add("citations-unsupported")
        identity = manifest.identity.model_dump(by_alias=True)
        if pin["mode"] == "pinned" and any(pin[key] != value for key, value in identity.items()):
            reasons.add("pin-mismatch")
        if observation is not None:
            if not observation.observed_at_ms <= now < observation.expires_at_ms:
                reasons.add("availability-stale")
            if observation.availability != "ready":
                reasons.add("runtime-unavailable")
            if task["taskKind"] not in observation.qualified_task_kinds or manifest.identity.evaluation_id is None:
                reasons.add("evaluation-unqualified")
            if observation.platform not in manifest.platforms:
                reasons.add("platform-unsupported")
            if observation.memory_mib < manifest.minimum_memory_mib or (
                manifest.accelerator != "none" and manifest.accelerator != observation.accelerator
            ):
                reasons.add("hardware-insufficient")
        if permission is not None:
            if requirements["dataClass"] != permission.data_class:
                reasons.add("classification-mismatch")
            if permission.data_class not in manifest.allowed_data_classes:
                reasons.add("data-class-denied")
            if manifest.deployment not in permission.permitted_deployments:
                reasons.add("deployment-denied")
            if not set(permission.required_modalities).issubset(manifest.modalities) or (
                observation is not None and not set(permission.required_modalities).issubset(observation.modalities)
            ):
                reasons.add("modality-unsupported")
            if permission.maximum_cost_microunits is not None:
                cost = manifest.cost_microunits_per_thousand_tokens
                if cost is None:
                    reasons.add("cost-unknown")
                elif (cost * (requirements["maxInputTokens"] + requirements["maxOutputTokens"]) + 999) // 1000 > (
                    permission.maximum_cost_microunits
                ):
                    reasons.add("cost-limit")
        return reasons
