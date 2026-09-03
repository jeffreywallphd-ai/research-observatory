import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import type { ProjectProjection, WorkflowProfileCatalogProjection } from "@research-observatory/contracts/core-api";

import { projectActionLabels, projectCompatibilityGuidance, ProjectsWorkspace } from "./ProjectsWorkspace";

const project: ProjectProjection = {
  schemaVersion: "1.0",
  projectId: "11111111-1111-4111-8111-111111111111",
  displayName: "Study One",
  templateId: "theory-synthesis",
  lifecycleState: "active",
  root: "C:/Research/study-one",
  open: false,
  accessMode: "closed",
  compatibilityState: "compatible",
  packageFormatVersion: "1.0.0",
  backupRequiredBeforeRepair: false,
  recoveryAction: "none",
  revision: 0,
  deleteConfirmation: "delete:11111111-1111-4111-8111-111111111111",
};

const catalog: WorkflowProfileCatalogProjection = {
  schemaVersion: "1.0",
  referenceId: "RO-UI-ACADEMIC-MINIMAL-1.5",
  referenceVersion: "1.5",
  profileCatalogVersion: "1.0.0",
  profileCatalogHash: `sha256:${"a".repeat(64)}`,
  allToolsAccessible: true,
  evidenceRequirementsUnchanged: true,
  provenanceRequirementsUnchanged: true,
  registeredToolPageContractIds: ["intent-contract.html", "theory-map.html"],
  profiles: [{
    profileId: "theory-synthesis",
    epistemicMode: "theory",
    title: "Theory synthesis",
    purpose: "Reconcile competing mechanisms into a bounded conceptual model.",
    example: "Reconcile competing mechanisms into a bounded conceptual model.",
    expectedOutputs: ["Theory map", "Traceable synthesis"],
    processForm: "revisitable",
    defaultEvidenceTypes: ["theoretical-work", "empirical-study"],
    defaultNoveltyStandard: "theoretical",
    defaultAutonomyLevel: "suggest",
    defaultStoppingConditions: ["interpretive-saturation"],
    warning: "Conceptual integration must preserve disagreements and evidentiary limits.",
    stages: [
      { stageKey: "intent-contract-1", order: 1, pageContractId: "intent-contract.html", label: "Research Intent", optional: false, rationale: "Set authority.", checkpointState: "unknown", checkpointRationale: "Not specified." },
      { stageKey: "theory-map-1", order: 2, pageContractId: "theory-map.html", label: "Theory Map", optional: false, rationale: "Map theory.", checkpointState: "unknown", checkpointRationale: "Not specified." },
    ],
  }],
};

describe("functional local projects workspace", () => {
  it("renders implemented create and open workflows without reference-only application pages", () => {
    const markup = renderToStaticMarkup(<ProjectsWorkspace announce={vi.fn()} initialCatalog={catalog} />);
    expect(markup).toContain('data-projects-workspace="true"');
    expect(markup).toContain("Create a local project");
    expect(markup).toContain("Open an existing project");
    expect(markup).toContain('id="project-parent-directory"');
    expect(markup).toContain('id="project-root"');
    expect(markup).toContain('id="project-research-objective"');
    expect(markup).toContain('id="project-primary-use-case"');
    expect(markup).toContain("Theory synthesis");
    expect(markup).toContain("Reconcile competing mechanisms");
    expect(markup).toContain("Theory map, Traceable synthesis");
    expect(markup).toContain("Revisitable process");
    expect(markup).toContain("Research Intent");
    expect(markup).toContain("Theory Map");
    expect(markup).toContain("All tools remain available");
    expect(markup).toContain("No project is selected");
    expect(markup).not.toContain("ui-reference");
    expect(markup).not.toContain("illustrative research");
  });

  it("derives only state-valid project lifecycle actions", () => {
    expect(projectActionLabels(project)).toEqual([
      "Open project",
      "Archive project",
      "Move to recoverable trash",
    ]);
    expect(projectActionLabels({ ...project, open: true })).toEqual(["Close project"]);
    expect(projectActionLabels({ ...project, lifecycleState: "archived" })).toEqual([
      "Restore project",
      "Move to recoverable trash",
    ]);
    expect(projectActionLabels({ ...project, lifecycleState: "trash" })).toEqual([]);
  });

  it("keeps incompatible projects read-only and presents a backup-first recovery path", () => {
    const newer: ProjectProjection = {
      ...project,
      open: true,
      accessMode: "read-only",
      compatibilityState: "newer-unsupported",
      packageFormatVersion: "2.0.0",
      backupRequiredBeforeRepair: true,
      recoveryAction: "backup-then-use-compatible-application",
    };
    expect(projectActionLabels(newer)).toEqual(["Close project"]);
    expect(projectActionLabels({ ...newer, open: false, accessMode: "closed" })).toEqual(["Open read-only"]);
    expect(projectActionLabels({
      ...newer,
      lifecycleState: "archived",
      open: false,
      accessMode: "closed",
    })).toEqual([]);
    expect(projectCompatibilityGuidance(newer)).toEqual({
      title: "Newer project format · read-only",
      message: "Keep the original unchanged. First create and verify a complete backup, then use a compatible application version with the working copy.",
    });
    expect(projectCompatibilityGuidance({
      ...newer,
      compatibilityState: "migration-required",
      packageFormatVersion: "0.9.0",
      recoveryAction: "backup-then-migrate",
    })?.message).toContain("First create and verify a complete backup");
  });
});
