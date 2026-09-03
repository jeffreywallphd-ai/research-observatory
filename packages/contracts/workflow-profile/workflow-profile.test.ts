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
    governedSupporting.stageKey = "application-settings-1";
    governedSupporting.pageContractId = "application-settings.html";
    governedSupporting.navigationRole = "supporting";
    governedSupporting.supportReturn = {
      primaryStageKey: stage.stageKey,
      primaryPageContractId: stage.pageContractId,
    };
    expect(workflowStageStateErrors(catalog, selection, governedSupporting)).toEqual([]);
    governedSupporting.pageContractId = "unregistered-tool.html";
    expect(workflowStageStateErrors(catalog, selection, governedSupporting)).toContain(
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
