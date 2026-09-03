import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  GOVERNED_WORKFLOW_CATALOG_SHA256,
  canonicalWorkflowProfileJson,
  decodeProjectWorkflowSelection,
  decodeWorkflowProfileCatalog,
  decodeWorkflowProfileMigration,
  decodeWorkflowStageState,
  projectWorkflowSelectionErrors,
  workflowProfileCatalogErrors,
  workflowProfileMigrationErrors,
  workflowProfileRecordSha256,
  workflowStageStateErrors,
} from "./generated";

const root = resolve(import.meta.dirname, "fixtures");
const fixture = (name: string): Record<string, any> =>
  JSON.parse(readFileSync(resolve(root, name), "utf8")) as Record<string, any>;
const clone = (value: Record<string, any>): Record<string, any> => JSON.parse(JSON.stringify(value));

describe("workflow profile contract", () => {
  it("binds exactly fourteen governed workflow profiles", () => {
    const catalog = fixture("approved-workflow-profile-catalog.v1.json");
    expect(workflowProfileCatalogErrors(catalog)).toEqual([]);
    const decoded = decodeWorkflowProfileCatalog(catalog);
    expect(decoded?.profiles).toHaveLength(14);
    expect(decoded?.registeredToolPageContractIds).toHaveLength(33);
    expect(decoded?.governedReference.workflowCatalogHash).toBe(GOVERNED_WORKFLOW_CATALOG_SHA256);
    expect(decoded?.profiles.every((profile: Record<string, any>) => profile.supportingToolPolicy.allRegisteredToolsAccessible)).toBe(true);
    const changed = clone(catalog);
    changed.profiles[0].title = "Unreviewed replacement";
    expect(workflowProfileCatalogErrors(changed)).toContain("catalog-binds-governed-reference");
    expect(decodeWorkflowProfileCatalog(changed)).toBeNull();
  });

  it("keeps selection revisions and profile-change impact immutable", () => {
    const catalog = fixture("approved-workflow-profile-catalog.v1.json");
    const initial = fixture("valid-project-workflow-selection.v1.json");
    const changed = fixture("valid-project-workflow-selection-change.v1.json");
    expect(projectWorkflowSelectionErrors(catalog, initial)).toEqual([]);
    expect(projectWorkflowSelectionErrors(catalog, changed)).toEqual([]);
    expect(changed.selectionId).toBe(initial.selectionId);
    expect(changed.selectionRevisionId).not.toBe(initial.selectionRevisionId);
    const decoded = decodeProjectWorkflowSelection(catalog, initial)!;
    const before = canonicalWorkflowProfileJson(decoded);
    initial.profile.profileId = "living-review";
    expect(canonicalWorkflowProfileJson(decoded)).toBe(before);
    expect(Object.isFrozen(decoded)).toBe(true);
    expect(Object.isFrozen(decoded.profile)).toBe(true);

    const missingPreview = clone(changed);
    missingPreview.impactPreview = null;
    expect(projectWorkflowSelectionErrors(catalog, missingPreview)).toContain("profile-change-binds-impact-preview");
    const skipped = clone(changed);
    skipped.parentSelection.revision = 2;
    expect(projectWorkflowSelectionErrors(catalog, skipped)).toContain("selection-lineage-is-immediate");
    const nonHuman = clone(initial);
    nonHuman.selectedBy.actorType = "system";
    expect(decodeProjectWorkflowSelection(catalog, nonHuman)).toBeNull();
  });

  it("separates workflow navigation state from analytical job state", () => {
    const catalog = fixture("approved-workflow-profile-catalog.v1.json");
    const selection = fixture("valid-project-workflow-selection.v1.json");
    const stage = fixture("valid-workflow-stage-state.v1.json");
    expect(workflowStageStateErrors(catalog, selection, stage)).toEqual([]);
    expect(decodeWorkflowStageState(catalog, selection, stage)).not.toBeNull();
    const overloaded = clone(stage);
    overloaded.jobId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d099";
    expect(decodeWorkflowStageState(catalog, selection, overloaded)).toBeNull();
    const invalidPass = clone(stage);
    invalidPass.passNumber = 2;
    expect(workflowStageStateErrors(catalog, selection, invalidPass)).toContain("stage-state-pass-matches-cycle-policy");
    const supporting = clone(stage);
    supporting.navigationRole = "supporting";
    supporting.supportReturn = null;
    expect(workflowStageStateErrors(catalog, selection, supporting)).toContain("supporting-tool-return-is-explicit");
    const governedSupporting = clone(stage);
    governedSupporting.stageStateId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d070";
    governedSupporting.stageStateRevisionId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d071";
    governedSupporting.revisionContentHash = `sha256:${"f".repeat(64)}`;
    governedSupporting.stageKey = "application-settings-1";
    governedSupporting.pageContractId = "application-settings.html";
    governedSupporting.navigationRole = "supporting";
    governedSupporting.supportReturn = {
      currentPrimaryState: {
        stageStateId: stage.stageStateId,
        stageStateRevisionId: stage.stageStateRevisionId,
        revision: stage.revision,
        revisionContentHash: stage.revisionContentHash,
        projectId: stage.projectId,
        selection: clone(stage.selection),
        profile: clone(stage.profile),
        stageKey: stage.stageKey,
        pageContractId: stage.pageContractId,
        passNumber: stage.passNumber,
        status: stage.status,
      },
    };
    expect(workflowStageStateErrors(catalog, selection, governedSupporting, stage)).toEqual([]);
    expect(workflowStageStateErrors(catalog, selection, governedSupporting)).toContain(
      "supporting-tool-return-is-explicit",
    );
    const substitutedStateHash = clone(governedSupporting);
    substitutedStateHash.supportReturn.currentPrimaryState.revisionContentHash = `sha256:${"9".repeat(64)}`;
    expect(workflowStageStateErrors(catalog, selection, substitutedStateHash, stage)).toContain(
      "supporting-tool-return-is-explicit",
    );
    const inventedAlias = clone(governedSupporting);
    inventedAlias.stageKey = "invented-support-alias";
    expect(workflowStageStateErrors(catalog, selection, inventedAlias, stage)).toContain(
      "supporting-tool-identity-is-governed",
    );
    const nonCurrentReturn = clone(governedSupporting);
    nonCurrentReturn.supportReturn.currentPrimaryState.stageKey = "source-manager-1";
    nonCurrentReturn.supportReturn.currentPrimaryState.pageContractId = "source-manager.html";
    expect(workflowStageStateErrors(catalog, selection, nonCurrentReturn, stage)).toContain(
      "supporting-tool-return-is-explicit",
    );
    governedSupporting.pageContractId = "unregistered-tool.html";
    expect(workflowStageStateErrors(catalog, selection, governedSupporting, stage)).toContain(
      "supporting-tool-is-governed-and-outside-primary-sequence",
    );
  });

  it("requires explicit complete profile migration while preserving history", () => {
    const catalog = fixture("approved-workflow-profile-catalog.v1.json");
    const migration = fixture("valid-workflow-profile-migration.v1.json");
    expect(workflowProfileMigrationErrors(catalog, migration)).toEqual([]);
    expect(decodeWorkflowProfileMigration(catalog, migration)).not.toBeNull();
    const missing = clone(migration);
    missing.stageMappings.pop();
    expect(workflowProfileMigrationErrors(catalog, missing)).toContain("migration-covers-prior-stages");
    const relabeledRetain = clone(migration);
    relabeledRetain.stageMappings[0].targetStageKey = "living-monitor-1";
    expect(workflowProfileMigrationErrors(catalog, relabeledRetain)).toContain(
      "migration-disposition-is-semantic",
    );
    const changed = fixture("valid-project-workflow-selection-change.v1.json");
    changed.impactPreview.priorStageStates[0].targetStageKey = "living-monitor-1";
    expect(projectWorkflowSelectionErrors(catalog, changed)).toContain("migration-disposition-is-semantic");
    const explicitMap = clone(migration);
    explicitMap.stageMappings[0].disposition = "map";
    explicitMap.stageMappings[0].targetStageKey = "living-monitor-1";
    expect(workflowProfileMigrationErrors(catalog, explicitMap)).toEqual([]);
    const missingRetainTarget = clone(migration);
    missingRetainTarget.stageMappings[0].targetStageKey = null;
    expect(workflowProfileMigrationErrors(catalog, missingRetainTarget)).toContain(
      "migration-disposition-is-semantic",
    );
    const reviewWithTarget = clone(migration);
    reviewWithTarget.stageMappings[1].targetStageKey = "living-monitor-1";
    expect(workflowProfileMigrationErrors(catalog, reviewWithTarget)).toContain(
      "migration-disposition-is-semantic",
    );
    const unchangedIntent = fixture("valid-project-workflow-selection-change.v1.json");
    unchangedIntent.researchIntent = clone(unchangedIntent.parentSelection.researchIntent);
    expect(projectWorkflowSelectionErrors(catalog, unchangedIntent)).toContain(
      "profile-change-binds-intent-and-human-acceptance",
    );
    const advancedIntent = fixture("valid-project-workflow-selection-change.v1.json");
    Object.assign(advancedIntent.acceptedMigration.priorResearchIntent, {
      revisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d023",
      revision: 3,
      revisionContentHash: `sha256:${"3".repeat(64)}`,
    });
    Object.assign(advancedIntent.acceptedMigration.targetResearchIntent, {
      revisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d024",
      revision: 4,
      revisionContentHash: `sha256:${"4".repeat(64)}`,
    });
    advancedIntent.researchIntent = clone(advancedIntent.acceptedMigration.targetResearchIntent);
    expect(projectWorkflowSelectionErrors(catalog, advancedIntent)).toEqual([]);
    const nonHumanAcceptance = clone(migration);
    nonHumanAcceptance.acceptance.decidedBy.actorType = "system";
    expect(decodeWorkflowProfileMigration(catalog, nonHumanAcceptance)).toBeNull();
    const missingAcceptance = clone(migration);
    delete missingAcceptance.acceptance;
    expect(decodeWorkflowProfileMigration(catalog, missingAcceptance)).toBeNull();
    const systemPrepared = clone(migration);
    systemPrepared.createdBy.actorType = "system";
    expect(workflowProfileMigrationErrors(catalog, systemPrepared)).toEqual([]);
    expect(changed.acceptedMigration.migrationId).toBe(migration.migrationId);
    expect(changed.acceptedMigration.migrationContentHash).toBe(migration.migrationContentHash);
    expect(changed.acceptedMigration.acceptance).toEqual(migration.acceptance);
    const substitutedMigration = fixture("valid-project-workflow-selection-change.v1.json");
    substitutedMigration.acceptedMigration.fromProfile = clone(substitutedMigration.profile);
    expect(projectWorkflowSelectionErrors(catalog, substitutedMigration)).toContain(
      "profile-change-binds-intent-and-human-acceptance",
    );
    const substitutedHuman = fixture("valid-project-workflow-selection-change.v1.json");
    substitutedHuman.acceptedMigration.acceptance.decidedBy.actorId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d099";
    expect(projectWorkflowSelectionErrors(catalog, substitutedHuman)).toContain(
      "profile-change-binds-intent-and-human-acceptance",
    );
    expect(migration.historyPolicy).toBe("preserve");
    expect(migration.requiresHumanAcceptance).toBe(true);
  });

  it("produces stable canonical hashes", () => {
    for (const value of [
      fixture("approved-workflow-profile-catalog.v1.json"),
      fixture("valid-project-workflow-selection.v1.json"),
      fixture("valid-project-workflow-selection-change.v1.json"),
      fixture("valid-workflow-stage-state.v1.json"),
      fixture("valid-workflow-profile-migration.v1.json"),
    ]) {
      const canonical = canonicalWorkflowProfileJson(value);
      expect(canonicalWorkflowProfileJson(JSON.parse(canonical))).toBe(canonical);
      expect(workflowProfileRecordSha256(value)).toMatch(/^sha256:[0-9a-f]{64}$/);
    }
  });
});
