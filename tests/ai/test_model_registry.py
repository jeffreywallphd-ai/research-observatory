from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services" / "core-api" / "src"))

from research_observatory_core.model_registry import ModelRegistry  # noqa: E402
from research_observatory_core.model_registry_contracts import (  # noqa: E402
    HostModelObservation,
    ModelManifest,
    ModelModality,
    ModelRegistryCatalog,
    RegistryDataClass,
    RegistryPermission,
    canonical_hash,
)
from research_observatory_core.ports.model_registry import EmptyModelInventory  # noqa: E402


def task() -> dict[str, Any]:
    return json.loads(
        (REPO / "packages/contracts/model-gateway/fixtures/valid-generation-task.v1.json").read_text("utf-8")
    )


def manifest_document() -> dict[str, Any]:
    pin = dict(task()["execution"])
    pin.pop("mode")
    return {
        "schemaVersion": "1.0",
        "manifestId": "fixture-scholar",
        "revision": 1,
        "identity": pin,
        "deployment": "local",
        "licenseId": "fixture-license",
        "capabilities": ["generation"],
        "features": ["structured-output"],
        "modalities": ["text"],
        "contextTokens": 8192,
        "maxOutputTokens": 1024,
        "supportsCitations": True,
        "platforms": ["windows-x64"],
        "minimumMemoryMiB": 2048,
        "accelerator": "none",
        "qualityTier": "balanced",
        "allowedDataClasses": ["confidential", "internal", "public"],
        "costMicrounitsPerThousandTokens": 0,
        "declaredAvailability": "available",
        "retired": False,
    }


class FixtureInventory:
    def __init__(self, manifests: tuple[ModelManifest, ...]) -> None:
        self.manifests = manifests
        self.observations = tuple(
            HostModelObservation(
                manifest_hash=canonical_hash(item),
                observed_at_ms=1000,
                expires_at_ms=2000,
                availability="ready",
                platform="windows-x64",
                memory_mib=8192,
                accelerator="none",
                qualified_task_kinds=("generation",),
                modalities=("text",),
            )
            for item in manifests
        )

    def discover(self) -> tuple[ModelManifest, ...]:
        return self.manifests

    def observe(self) -> tuple[HostModelObservation, ...]:
        return self.observations


class FixturePolicy:
    """Synthetic canonical policy/rights authority, never a production allow-all."""

    def __init__(self) -> None:
        self.reason_codes: tuple[str, ...] = ()
        self.data_class: RegistryDataClass = "confidential"
        self.required_modalities: tuple[ModelModality, ...] = ("text",)
        self.expires_at_ms = 2000
        self.wrong_task = False

    def assess(
        self, *, project_id: str, catalog_revision: int, task: object, manifest: ModelManifest
    ) -> RegistryPermission:
        return RegistryPermission(
            project_id=project_id,
            catalog_revision=catalog_revision,
            task_hash="sha256:" + "0" * 64 if self.wrong_task else canonical_hash(task),
            manifest_hash=canonical_hash(manifest),
            policy_revision="fixture-policy-1",
            rights_revision="fixture-rights-1",
            observed_at_ms=1000,
            expires_at_ms=self.expires_at_ms,
            data_class=self.data_class,
            required_modalities=self.required_modalities,
            permitted_deployments=("local",),
            maximum_cost_microunits=100,
            reason_codes=self.reason_codes,
        )


class ModelRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = ModelManifest.model_validate(manifest_document())
        self.inventory = FixtureInventory((self.manifest,))
        self.policy = FixturePolicy()
        self.catalog = ModelRegistryCatalog(project_id="fixture-project", revision=1, manifests=(self.manifest,))

    def resolve(self, candidate: dict[str, Any] | None = None) -> Any:
        return ModelRegistry(self.inventory, self.policy, clock_ms=lambda: 1500).resolve(
            self.catalog,
            task() if candidate is None else candidate,
        )

    def test_eligible_candidate_binds_exact_catalog_task_manifest_and_policy(self) -> None:
        result = self.resolve()
        self.assertEqual(("fixture-scholar",), tuple(item.manifest_id for item in result.eligible))
        selected = result.eligible[0]
        self.assertEqual(canonical_hash(self.manifest), selected.manifest_hash)
        self.assertEqual("fixture-policy-1", selected.policy_revision)
        self.assertEqual("fixture-rights-1", selected.rights_revision)
        self.assertEqual(canonical_hash(task()), result.task_hash)
        self.assertEqual(1, result.catalog_revision)
        self.assertFalse(result.execution_authorized)

    def test_manifest_owns_nested_metadata_and_rejects_invalid_or_extra_values(self) -> None:
        value = manifest_document()
        decoded = ModelManifest.model_validate(value)
        value["features"].clear()
        self.assertEqual(("structured-output",), decoded.features)
        with self.assertRaises(ValidationError):
            decoded.identity.model_id = "substituted"
        for field, invalid in (
            ("revision", True),
            ("contextTokens", "8192"),
            ("minimumMemoryMiB", -1),
            ("costMicrounitsPerThousandTokens", float("nan")),
            ("features", ["x", "x"]),
            ("licenseId", "file:///private/license"),
            ("capabilities", []),
            ("allowed", True),
        ):
            value = manifest_document()
            value[field] = invalid
            with self.subTest(field=field), self.assertRaises(ValidationError):
                ModelManifest.model_validate(value)

    def test_each_capability_resource_and_license_boundary_denies(self) -> None:
        for field, replacement, reason in (
            ("capabilities", ["embedding"], "task-kind-unsupported"),
            ("features", [], "required-feature-unsupported"),
            ("modalities", ["image"], "modality-unsupported"),
            ("contextTokens", 4096, "context-limit"),
            ("maxOutputTokens", 1, "output-limit"),
            ("supportsCitations", False, "citations-unsupported"),
            ("minimumMemoryMiB", 16384, "hardware-insufficient"),
            ("platforms", ["linux-x64"], "platform-unsupported"),
            ("accelerator", "gpu", "hardware-insufficient"),
            ("allowedDataClasses", ["public"], "data-class-denied"),
            ("retired", True, "model-retired"),
            ("deployment", "remote", "deployment-denied"),
            ("costMicrounitsPerThousandTokens", None, "cost-unknown"),
            ("costMicrounitsPerThousandTokens", 1000, "cost-limit"),
        ):
            value = manifest_document()
            value[field] = replacement
            manifest = ModelManifest.model_validate(value)
            self.catalog = ModelRegistryCatalog(project_id="fixture-project", revision=1, manifests=(manifest,))
            self.inventory = FixtureInventory((manifest,))
            with self.subTest(field=field):
                result = self.resolve()
                self.assertFalse(result.eligible)
                self.assertIn(reason, result.rejected[0].reason_codes)

    def test_every_reproducibility_pin_is_exact(self) -> None:
        for field in task()["execution"]:
            if field == "mode":
                continue
            candidate = task()
            candidate["execution"][field] = (
                "sha256:" + "a" * 64
                if field == "configurationHash"
                else "9.9.9"
                if "Version" in field
                else "different-id"
            )
            with self.subTest(field=field):
                result = self.resolve(candidate)
                self.assertFalse(result.eligible)
                self.assertIn("pin-mismatch", result.rejected[0].reason_codes)

    def test_catalog_does_not_confer_readiness_and_stale_or_conflicting_observations_deny(self) -> None:
        ready = self.inventory.observations[0].model_dump()
        for observations, reason in (
            ((), "availability-unknown"),
            ((HostModelObservation(**(ready | {"expires_at_ms": 1400})),), "availability-stale"),
            ((HostModelObservation(**(ready | {"availability": "unavailable"})),), "runtime-unavailable"),
            ((HostModelObservation(**(ready | {"qualified_task_kinds": ()})),), "evaluation-unqualified"),
            ((HostModelObservation(**(ready | {"observed_at_ms": 1600})),), "availability-stale"),
            ((self.inventory.observations[0], self.inventory.observations[0]), "observation-ambiguous"),
        ):
            self.inventory.observations = observations
            with self.subTest(reason=reason):
                result = self.resolve()
                self.assertFalse(result.eligible)
                self.assertIn(reason, result.rejected[0].reason_codes)
        self.assertEqual((), EmptyModelInventory().discover())
        self.assertEqual((), EmptyModelInventory().observe())

    def test_rights_policy_freshness_and_classification_are_independent_denials(self) -> None:
        self.policy.reason_codes = ("source-license-denied",)
        self.assertIn("source-license-denied", self.resolve().rejected[0].reason_codes)
        self.policy.reason_codes = ()
        self.policy.expires_at_ms = 1400
        self.assertIn("permission-stale", self.resolve().rejected[0].reason_codes)
        self.policy.expires_at_ms = 2000
        self.policy.wrong_task = True
        self.assertIn("permission-identity-mismatch", self.resolve().rejected[0].reason_codes)
        self.policy.wrong_task = False
        candidate = task()
        candidate["requirements"]["dataClass"] = "public"
        self.assertIn("classification-mismatch", self.resolve(candidate).rejected[0].reason_codes)

    def test_witness_expiry_during_lookup_is_not_eligible(self) -> None:
        for witness in ("permission", "inventory"):
            for completed_at in (1999, 2000):
                with self.subTest(witness=witness, completed_at=completed_at):
                    now = [1500]
                    inventory = FixtureInventory(self.catalog.manifests)
                    policy = FixturePolicy()
                    lookup: Any

                    def clock_ms(current: list[int] = now) -> int:
                        return current[0]

                    if witness == "permission":
                        inventory.observations = tuple(
                            item.model_copy(update={"expires_at_ms": 3000}) for item in inventory.observations
                        )
                        assess = policy.assess

                        def delayed_assess(_assess=assess, _now=now, _completed_at=completed_at, **kwargs):
                            result = _assess(**kwargs)
                            _now[0] = _completed_at
                            return result

                        lookup = patch.object(policy, "assess", delayed_assess)
                    else:
                        policy.expires_at_ms = 3000
                        observe = inventory.observe

                        def delayed_observe(_observe=observe, _now=now, _completed_at=completed_at):
                            result = _observe()
                            _now[0] = _completed_at
                            return result

                        lookup = patch.object(inventory, "observe", delayed_observe)
                    with lookup:
                        result = ModelRegistry(inventory, policy, clock_ms=clock_ms).resolve(self.catalog, task())
                    self.assertEqual(completed_at < 2000, bool(result.eligible))
                    if completed_at == 2000:
                        reason = "permission-stale" if witness == "permission" else "availability-stale"
                        self.assertEqual((reason,), result.rejected[0].reason_codes)

    def test_later_manifest_lookup_cannot_return_an_expired_earlier_candidate(self) -> None:
        alternate = self.manifest.model_copy(update={"manifest_id": "fixture-second"})
        catalog = self.catalog.model_copy(update={"manifests": (self.manifest, alternate)})
        for witness in ("permission", "inventory"):
            with self.subTest(witness=witness):
                now = [1500]
                calls = [0]
                inventory = FixtureInventory(catalog.manifests)
                inventory.observations = tuple(
                    item.model_copy(update={"expires_at_ms": 2000 if witness == "inventory" and index == 0 else 3000})
                    for index, item in enumerate(inventory.observations)
                )
                policy = FixturePolicy()
                policy.expires_at_ms = 3000
                assess = policy.assess

                def clock_ms(current: list[int] = now) -> int:
                    return current[0]

                def delayed_assess(_assess=assess, _calls=calls, _witness=witness, _now=now, **kwargs):
                    result = _assess(**kwargs)
                    _calls[0] += 1
                    if _witness == "permission" and kwargs["manifest"].manifest_id == self.manifest.manifest_id:
                        result = result.model_copy(update={"expires_at_ms": 2000})
                    if _calls[0] == 2:
                        _now[0] = 2000
                    return result

                with patch.object(policy, "assess", delayed_assess):
                    result = ModelRegistry(inventory, policy, clock_ms=clock_ms).resolve(catalog, task())
                self.assertEqual((alternate.manifest_id,), tuple(item.manifest_id for item in result.eligible))
                self.assertEqual(self.manifest.manifest_id, result.rejected[0].manifest_id)
                reason = "permission-stale" if witness == "permission" else "availability-stale"
                self.assertEqual((reason,), result.rejected[0].reason_codes)

    def test_invalid_task_does_not_call_policy_or_inventory(self) -> None:
        class ForbiddenInventory(FixtureInventory):
            def observe(self) -> tuple[HostModelObservation, ...]:
                raise AssertionError("invalid task crossed inventory boundary")

        result = ModelRegistry(ForbiddenInventory(()), self.policy).resolve(self.catalog, {"allow": True})
        self.assertEqual(("model-task-invalid",), result.reason_codes)
        self.assertFalse(result.eligible)

    def test_missing_or_unavailable_policy_never_confers_eligibility(self) -> None:
        class FailedPolicy(FixturePolicy):
            def assess(self, **_arguments: Any) -> RegistryPermission:
                raise OSError("synthetic unavailable policy")

        for policy in (None, FailedPolicy()):
            with self.subTest(policy=type(policy).__name__):
                result = ModelRegistry(self.inventory, policy, clock_ms=lambda: 1500).resolve(self.catalog, task())
                self.assertFalse(result.eligible)
                self.assertIn("permission-unavailable", result.rejected[0].reason_codes)

    def test_maximum_policy_denials_combine_with_local_failures_without_losing_reasons(self) -> None:
        self.policy.reason_codes = tuple(f"policy-denial-{index:02d}" for index in range(32))
        self.inventory.observations = ()
        result = self.resolve()
        self.assertFalse(result.eligible)
        self.assertEqual(("no-eligible-model",), result.reason_codes)
        self.assertEqual(
            tuple(sorted((*self.policy.reason_codes, "availability-unknown"))), result.rejected[0].reason_codes
        )

    def test_thousand_manifest_matching_is_bounded_and_deterministic(self) -> None:
        manifests = []
        for index in range(1000):
            value = manifest_document()
            value["manifestId"] = f"fixture-{index:04}"
            manifests.append(ModelManifest.model_validate(value))
        catalog = ModelRegistryCatalog(project_id="fixture-project", revision=1, manifests=tuple(manifests))
        registry = ModelRegistry(FixtureInventory(catalog.manifests), self.policy, clock_ms=lambda: 1500)
        started = time.perf_counter()
        result = registry.resolve(catalog, task())
        elapsed = time.perf_counter() - started
        self.assertEqual(1000, len(result.eligible))
        self.assertEqual(
            tuple(item.manifest_id for item in manifests), tuple(item.manifest_id for item in result.eligible)
        )
        self.assertLess(elapsed, 0.1, f"1,000-manifest filtering/ranking took {elapsed:.6f}s")


if __name__ == "__main__":
    unittest.main()
