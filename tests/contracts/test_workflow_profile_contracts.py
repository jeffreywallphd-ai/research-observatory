from __future__ import annotations

import copy
import json
import sys
import unittest
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker

REPO = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = REPO / "packages" / "contracts" / "workflow-profile"
sys.path.insert(0, str(REPO / "services" / "core-api" / "src"))

from research_observatory_core.workflow_profile_contracts import (  # noqa: E402
    GOVERNED_WORKFLOW_CATALOG_SHA256,
    WORKFLOW_PROFILE_SCHEMA_SHA256,
    canonical_workflow_profile_json,
    decode_project_workflow_selection,
    decode_workflow_profile_catalog,
    decode_workflow_profile_migration,
    decode_workflow_stage_state,
    project_workflow_selection_errors,
    workflow_profile_catalog_errors,
    workflow_profile_migration_errors,
    workflow_profile_record_sha256,
    workflow_stage_state_errors,
)


def fixture(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((CONTRACT_ROOT / "fixtures" / name).read_text(encoding="utf-8")))


class WorkflowProfileContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = fixture("approved-workflow-profile-catalog.v1.json")
        self.selection = fixture("valid-project-workflow-selection.v1.json")

    def test_governed_catalog_is_exact_hash_bound_and_has_all_fourteen_profiles(self) -> None:
        schema_text = (
            (CONTRACT_ROOT / "workflow-profile.schema.json")
            .read_text(encoding="utf-8")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
        )
        schema = json.loads(schema_text)
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        self.assertEqual([], list(validator.iter_errors(self.catalog)))
        self.assertEqual((), workflow_profile_catalog_errors(self.catalog))
        decoded = decode_workflow_profile_catalog(self.catalog)
        self.assertIsNotNone(decoded)
        assert decoded is not None
        snapshot = cast(Any, decoded)
        self.assertEqual(14, len(snapshot["profiles"]))
        self.assertEqual(33, len(snapshot["registeredToolPageContractIds"]))
        self.assertEqual("RO-UI-ACADEMIC-MINIMAL-1.5", snapshot["governedReference"]["referenceId"])
        self.assertEqual(GOVERNED_WORKFLOW_CATALOG_SHA256, snapshot["governedReference"]["workflowCatalogHash"])
        self.assertEqual(sha256(schema_text.encode("utf-8")).hexdigest(), WORKFLOW_PROFILE_SCHEMA_SHA256)
        for profile in snapshot["profiles"]:
            self.assertEqual(
                list(range(1, len(profile["stages"]) + 1)), [stage["order"] for stage in profile["stages"]]
            )
            self.assertTrue(profile["supportingToolPolicy"]["allRegisteredToolsAccessible"])
            self.assertTrue(profile["expectedOutputs"])

    def test_catalog_drift_unknown_fields_and_future_contracts_fail_closed(self) -> None:
        changed = copy.deepcopy(self.catalog)
        changed["profiles"][0]["title"] = "Unreviewed replacement"
        self.assertIn("catalog-binds-governed-reference", workflow_profile_catalog_errors(changed))
        self.assertIsNone(decode_workflow_profile_catalog(changed))

        injected = copy.deepcopy(self.catalog)
        injected["credential"] = "secret"
        self.assertIsNone(decode_workflow_profile_catalog(injected))

        future = copy.deepcopy(self.catalog)
        future["contractVersion"] = "2.0.0"
        self.assertIsNone(decode_workflow_profile_catalog(future))

    def test_selection_revision_binds_intent_catalog_profile_and_immutable_predecessor(self) -> None:
        self.assertEqual((), project_workflow_selection_errors(self.catalog, self.selection))
        decoded = decode_project_workflow_selection(self.catalog, self.selection)
        self.assertIsNotNone(decoded)
        assert decoded is not None
        before = canonical_workflow_profile_json(decoded)
        self.selection["profile"]["profileId"] = "living-review"
        self.assertEqual(before, canonical_workflow_profile_json(decoded))
        with self.assertRaises(TypeError):
            cast(Any, decoded)["profile"]["profileId"] = "rapid-orientation"

        changed = fixture("valid-project-workflow-selection-change.v1.json")
        self.assertEqual((), project_workflow_selection_errors(self.catalog, changed))
        self.assertEqual(self.selection["selectionId"], changed["selectionId"])
        self.assertNotEqual(self.selection["selectionRevisionId"], changed["selectionRevisionId"])
        self.assertEqual(1, len(changed["impactPreview"]["priorStageStates"]))
        self.assertEqual("preserve", changed["impactPreview"]["historyPolicy"])

        skipped = copy.deepcopy(changed)
        skipped["parentSelection"]["revision"] = 2
        self.assertIn("selection-lineage-is-immediate", project_workflow_selection_errors(self.catalog, skipped))
        missing_preview = copy.deepcopy(changed)
        missing_preview["impactPreview"] = None
        self.assertIn(
            "profile-change-binds-impact-preview", project_workflow_selection_errors(self.catalog, missing_preview)
        )
        substituted = copy.deepcopy(changed)
        substituted["impactPreview"]["priorSelection"]["selectionRevisionId"] = substituted["selectionRevisionId"]
        self.assertIn(
            "profile-change-binds-impact-preview", project_workflow_selection_errors(self.catalog, substituted)
        )
        non_human = copy.deepcopy(self.selection)
        non_human["selectedBy"]["actorType"] = "system"
        self.assertIsNone(decode_project_workflow_selection(self.catalog, non_human))
        collapsed_identity = copy.deepcopy(self.selection)
        collapsed_identity["selectionRevisionId"] = collapsed_identity["selectionId"]
        self.assertIn(
            "selection-binds-catalog-profile-and-intent",
            project_workflow_selection_errors(self.catalog, collapsed_identity),
        )

    def test_stage_state_represents_navigation_not_analytical_job_state(self) -> None:
        stage = fixture("valid-workflow-stage-state.v1.json")
        self.assertEqual((), workflow_stage_state_errors(self.catalog, self.selection, stage))
        self.assertIsNotNone(decode_workflow_stage_state(self.catalog, self.selection, stage))

        for status in ("current", "completed", "attention-required", "blocked", "stale", "skipped-with-rationale"):
            with self.subTest(status=status):
                candidate = copy.deepcopy(stage)
                candidate["status"] = status
                candidate["completionEvidenceIds"] = [f"sha256:{'c' * 64}"] if status == "completed" else []
                candidate["attention"] = (
                    {"reasonCode": "researcher-review", "rationale": "Review required."}
                    if status in {"attention-required", "blocked"}
                    else None
                )
                candidate["staleCauses"] = [f"sha256:{'d' * 64}"] if status == "stale" else []
                candidate["skipRationale"] = (
                    "The researcher explicitly skipped this optional stage."
                    if status == "skipped-with-rationale"
                    else None
                )
                self.assertEqual((), workflow_stage_state_errors(self.catalog, self.selection, candidate))

        invalid_pass = copy.deepcopy(stage)
        invalid_pass["passNumber"] = 2
        self.assertIn(
            "stage-state-pass-matches-cycle-policy",
            workflow_stage_state_errors(self.catalog, self.selection, invalid_pass),
        )
        collapsed_state_identity = copy.deepcopy(stage)
        collapsed_state_identity["stageStateRevisionId"] = collapsed_state_identity["stageStateId"]
        self.assertIn(
            "stage-state-binds-selection-and-profile",
            workflow_stage_state_errors(self.catalog, self.selection, collapsed_state_identity),
        )
        system_stale = copy.deepcopy(stage)
        system_stale["status"] = "stale"
        system_stale["staleCauses"] = [f"sha256:{'e' * 64}"]
        system_stale["updatedBy"]["actorType"] = "system"
        self.assertEqual((), workflow_stage_state_errors(self.catalog, self.selection, system_stale))

        overloaded = copy.deepcopy(stage)
        overloaded["jobId"] = "018f47a2-4d6b-7f78-9f2e-7fb76c86d099"
        self.assertIsNone(decode_workflow_stage_state(self.catalog, self.selection, overloaded))
        unsupported = copy.deepcopy(stage)
        unsupported["navigationRole"] = "supporting"
        unsupported["supportReturn"] = None
        self.assertIn(
            "supporting-tool-return-is-explicit", workflow_stage_state_errors(self.catalog, self.selection, unsupported)
        )

        supporting = copy.deepcopy(stage)
        supporting["stageStateId"] = "018f47a2-4d6b-7f78-9f2e-7fb76c86d070"
        supporting["stageStateRevisionId"] = "018f47a2-4d6b-7f78-9f2e-7fb76c86d071"
        supporting["revisionContentHash"] = f"sha256:{'f' * 64}"
        supporting["stageKey"] = "application-settings-1"
        supporting["pageContractId"] = "application-settings.html"
        supporting["navigationRole"] = "supporting"
        supporting["supportReturn"] = {
            "currentPrimaryState": {
                "stageStateId": stage["stageStateId"],
                "stageStateRevisionId": stage["stageStateRevisionId"],
                "revision": stage["revision"],
                "revisionContentHash": stage["revisionContentHash"],
                "projectId": stage["projectId"],
                "selection": copy.deepcopy(stage["selection"]),
                "profile": copy.deepcopy(stage["profile"]),
                "stageKey": stage["stageKey"],
                "pageContractId": stage["pageContractId"],
                "passNumber": stage["passNumber"],
                "status": stage["status"],
            }
        }
        self.assertEqual((), workflow_stage_state_errors(self.catalog, self.selection, supporting, stage))
        self.assertIn(
            "supporting-tool-return-is-explicit",
            workflow_stage_state_errors(self.catalog, self.selection, supporting),
        )
        substituted_state_hash = copy.deepcopy(supporting)
        substituted_state_hash["supportReturn"]["currentPrimaryState"]["revisionContentHash"] = f"sha256:{'9' * 64}"
        self.assertIn(
            "supporting-tool-return-is-explicit",
            workflow_stage_state_errors(self.catalog, self.selection, substituted_state_hash, stage),
        )
        invented_alias = copy.deepcopy(supporting)
        invented_alias["stageKey"] = "invented-support-alias"
        self.assertIn(
            "supporting-tool-identity-is-governed",
            workflow_stage_state_errors(self.catalog, self.selection, invented_alias, stage),
        )
        non_current_return = copy.deepcopy(supporting)
        non_current_return["supportReturn"]["currentPrimaryState"]["stageKey"] = "source-manager-1"
        non_current_return["supportReturn"]["currentPrimaryState"]["pageContractId"] = "source-manager.html"
        self.assertIn(
            "supporting-tool-return-is-explicit",
            workflow_stage_state_errors(self.catalog, self.selection, non_current_return, stage),
        )
        supporting["pageContractId"] = "unregistered-tool.html"
        self.assertIn(
            "supporting-tool-is-governed-and-outside-primary-sequence",
            workflow_stage_state_errors(self.catalog, self.selection, supporting, stage),
        )

    def test_profile_migration_maps_every_prior_stage_without_rewriting_history(self) -> None:
        migration = fixture("valid-workflow-profile-migration.v1.json")
        self.assertEqual((), workflow_profile_migration_errors(self.catalog, migration))
        self.assertIsNotNone(decode_workflow_profile_migration(self.catalog, migration))
        self.assertTrue(migration["requiresHumanAcceptance"])
        self.assertEqual("preserve", migration["historyPolicy"])

        missing = copy.deepcopy(migration)
        missing["stageMappings"].pop()
        self.assertIn("migration-covers-prior-stages", workflow_profile_migration_errors(self.catalog, missing))
        duplicate = copy.deepcopy(migration)
        duplicate["stageMappings"][1]["fromStageKey"] = duplicate["stageMappings"][0]["fromStageKey"]
        self.assertIn("migration-covers-prior-stages", workflow_profile_migration_errors(self.catalog, duplicate))
        relabeled_retain = copy.deepcopy(migration)
        relabeled_retain["stageMappings"][0]["targetStageKey"] = "living-monitor-1"
        self.assertIn(
            "migration-disposition-is-semantic",
            workflow_profile_migration_errors(self.catalog, relabeled_retain),
        )
        changed = fixture("valid-project-workflow-selection-change.v1.json")
        changed["impactPreview"]["priorStageStates"][0]["targetStageKey"] = "living-monitor-1"
        self.assertIn(
            "migration-disposition-is-semantic",
            project_workflow_selection_errors(self.catalog, changed),
        )
        explicit_map = copy.deepcopy(migration)
        explicit_map["stageMappings"][0]["disposition"] = "map"
        explicit_map["stageMappings"][0]["targetStageKey"] = "living-monitor-1"
        self.assertEqual((), workflow_profile_migration_errors(self.catalog, explicit_map))
        missing_retain_target = copy.deepcopy(migration)
        missing_retain_target["stageMappings"][0]["targetStageKey"] = None
        self.assertIn(
            "migration-disposition-is-semantic",
            workflow_profile_migration_errors(self.catalog, missing_retain_target),
        )
        review_with_target = copy.deepcopy(migration)
        review_with_target["stageMappings"][1]["targetStageKey"] = "living-monitor-1"
        self.assertIn(
            "migration-disposition-is-semantic",
            workflow_profile_migration_errors(self.catalog, review_with_target),
        )
        unchanged_intent = fixture("valid-project-workflow-selection-change.v1.json")
        unchanged_intent["researchIntent"] = copy.deepcopy(unchanged_intent["parentSelection"]["researchIntent"])
        self.assertIn(
            "profile-change-binds-intent-and-human-acceptance",
            project_workflow_selection_errors(self.catalog, unchanged_intent),
        )
        advanced_intent = fixture("valid-project-workflow-selection-change.v1.json")
        advanced_prior = advanced_intent["acceptedMigration"]["priorResearchIntent"]
        advanced_prior.update(
            {
                "revisionId": "018f47a2-4d6b-7f78-9f2e-7fb76c86d023",
                "revision": 3,
                "revisionContentHash": "sha256:" + "3" * 64,
            }
        )
        advanced_target = advanced_intent["acceptedMigration"]["targetResearchIntent"]
        advanced_target.update(
            {
                "revisionId": "018f47a2-4d6b-7f78-9f2e-7fb76c86d024",
                "revision": 4,
                "revisionContentHash": "sha256:" + "4" * 64,
            }
        )
        advanced_intent["researchIntent"] = copy.deepcopy(advanced_target)
        self.assertEqual((), project_workflow_selection_errors(self.catalog, advanced_intent))
        non_human_acceptance = copy.deepcopy(migration)
        non_human_acceptance["acceptance"]["decidedBy"]["actorType"] = "system"
        self.assertIsNone(decode_workflow_profile_migration(self.catalog, non_human_acceptance))
        missing_acceptance = copy.deepcopy(migration)
        del missing_acceptance["acceptance"]
        self.assertIsNone(decode_workflow_profile_migration(self.catalog, missing_acceptance))
        system_prepared = copy.deepcopy(migration)
        system_prepared["createdBy"]["actorType"] = "system"
        self.assertEqual((), workflow_profile_migration_errors(self.catalog, system_prepared))
        accepted_migration = fixture("valid-project-workflow-selection-change.v1.json")["acceptedMigration"]
        self.assertEqual(migration["migrationId"], accepted_migration["migrationId"])
        self.assertEqual(migration["migrationContentHash"], accepted_migration["migrationContentHash"])
        self.assertEqual(migration["acceptance"], accepted_migration["acceptance"])
        substituted_migration = fixture("valid-project-workflow-selection-change.v1.json")
        substituted_migration["acceptedMigration"]["fromProfile"] = copy.deepcopy(substituted_migration["profile"])
        self.assertIn(
            "profile-change-binds-intent-and-human-acceptance",
            project_workflow_selection_errors(self.catalog, substituted_migration),
        )
        substituted_human = fixture("valid-project-workflow-selection-change.v1.json")
        substituted_human["acceptedMigration"]["acceptance"]["decidedBy"]["actorId"] = (
            "018f47a2-4d6b-7f78-9f2e-7fb76c86d099"
        )
        self.assertIn(
            "profile-change-binds-intent-and-human-acceptance",
            project_workflow_selection_errors(self.catalog, substituted_human),
        )

    def test_canonical_hashes_are_stable_across_reload(self) -> None:
        for value in (
            self.catalog,
            self.selection,
            fixture("valid-project-workflow-selection-change.v1.json"),
            fixture("valid-workflow-stage-state.v1.json"),
            fixture("valid-workflow-profile-migration.v1.json"),
        ):
            canonical = canonical_workflow_profile_json(value)
            self.assertEqual(canonical, canonical_workflow_profile_json(json.loads(canonical)))
            self.assertEqual(
                f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}", workflow_profile_record_sha256(value)
            )


if __name__ == "__main__":
    unittest.main()
