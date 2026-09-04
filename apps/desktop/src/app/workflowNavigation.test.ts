import { describe, expect, it } from "vitest";

import type {
  WorkflowProfileCatalogProjection,
  WorkflowProgressProjection,
} from "@research-observatory/contracts/core-api";

import {
  IMPLEMENTED_WORKSPACES,
  WorkflowContextLoader,
  createSupportingReturn,
  createWorkflowAuthoritySnapshot,
  deriveWorkflowStages,
  selectPrimaryStage,
  stageDisplayLabel,
  supportingReturnMatches,
  workspaceClassification,
  type WorkflowAuthoritySnapshot,
  type WorkflowStageAuthorityState,
} from "./workflowNavigationModel";

const checkpointRationale = "No checkpoint authority is declared by the approved reference.";

function stage(
  stageKey: string,
  order: number,
  pageContractId: string,
  optional = false,
) {
  return {
    stageKey,
    order,
    pageContractId,
    label: pageContractId.replace(".html", ""),
    optional,
    rationale: `Why ${stageKey} matters.`,
    checkpointState: "unknown" as const,
    checkpointRationale,
  };
}

function profile(
  profileId: "systematic-review" | "theory-synthesis" | "manuscript-review-revision",
  processForm: "linear" | "revisitable",
  stages: ReturnType<typeof stage>[],
) {
  return {
    profileId,
    epistemicMode: profileId === "theory-synthesis" ? "theory" as const : profileId === "manuscript-review-revision" ? "empirical" as const : "systematic" as const,
    title: profileId,
    purpose: `Purpose for ${profileId}.`,
    example: `Example for ${profileId}.`,
    expectedOutputs: [`Output for ${profileId}.`],
    processForm,
    defaultEvidenceTypes: ["theoretical-work" as const],
    defaultNoveltyStandard: "not-claimed" as const,
    defaultAutonomyLevel: "suggest" as const,
    defaultStoppingConditions: ["researcher-decision" as const],
    warning: `Warning for ${profileId}.`,
    stages,
  };
}

const catalog = {
  schemaVersion: "1.0",
  referenceId: "RO-UI-ACADEMIC-MINIMAL-1.5",
  referenceVersion: "1.5",
  profileCatalogVersion: "1.0.0",
  profileCatalogHash: `sha256:${"a".repeat(64)}`,
  intentGuidanceVersion: "1.0.0",
  intentGuidanceHash: `sha256:${"b".repeat(64)}`,
  allToolsAccessible: true,
  evidenceRequirementsUnchanged: true,
  provenanceRequirementsUnchanged: true,
  registeredToolPageContractIds: IMPLEMENTED_WORKSPACES.flatMap(({ pageContractIds }) => pageContractIds),
  profiles: [
    profile("systematic-review", "linear", [
      stage("intent-contract-1", 1, "intent-contract.html"),
      stage("task-center-1", 2, "task-center.html", true),
      stage("audit-lineage-1", 3, "audit-lineage.html"),
    ]),
    profile("theory-synthesis", "linear", [
      stage("intent-contract-1", 1, "intent-contract.html"),
      stage("audit-lineage-1", 2, "audit-lineage.html"),
      stage("theory-map-1", 3, "theory-map.html"),
    ]),
    profile("manuscript-review-revision", "revisitable", [
      stage("intent-contract-1", 1, "intent-contract.html"),
      stage("manuscript-studio-1", 2, "manuscript-studio.html"),
      stage("manuscript-studio-2", 3, "manuscript-studio.html"),
      stage("audit-lineage-1", 4, "audit-lineage.html"),
    ]),
  ],
} satisfies WorkflowProfileCatalogProjection;

function authority(
  primaryUseCase: "systematic-review" | "theory-synthesis" | "manuscript-review-revision" = "systematic-review",
): WorkflowAuthoritySnapshot {
  const result = createWorkflowAuthoritySnapshot(
    {
      projectId: "11111111-1111-4111-8111-111111111111",
      root: "C:/Research/current-project",
      open: true,
      compatibilityState: "compatible",
    },
    catalog,
    {
      projectId: "11111111-1111-4111-8111-111111111111",
      current: {
        revisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d041",
        revisionContentHash: `sha256:${"c".repeat(64)}`,
        primaryUseCase,
      },
    },
  );
  if (!result) throw new Error("test authority did not resolve");
  return result;
}

describe("workflow navigation model", () => {
  it("derives exact profile-relative order without inventing completion on route visits", () => {
    const systematic = authority("systematic-review");
    const theory = authority("theory-synthesis");

    expect(deriveWorkflowStages(systematic).map(({ stageKey }) => stageKey)).toEqual([
      "intent-contract-1", "task-center-1", "audit-lineage-1",
    ]);
    expect(deriveWorkflowStages(theory).map(({ stageKey }) => stageKey)).toEqual([
      "intent-contract-1", "audit-lineage-1", "theory-map-1",
    ]);

    const visited = selectPrimaryStage(systematic, "audit-lineage-1");
    expect(visited?.workspace).toBe("audit");
    expect(deriveWorkflowStages(visited!.authority).map(({ state }) => state)).toEqual([
      "upcoming", "upcoming", "current",
    ]);
  });

  it("renders every authoritative state with text semantics while optionality and cycles remain explicit", () => {
    const states: readonly WorkflowStageAuthorityState[] = [
      "not-started", "available", "current", "in-progress", "attention-required",
      "blocked", "completed", "stale", "skipped-with-rationale",
    ];
    expect(states.map(stageDisplayLabel)).toEqual([
      "Not started", "Available", "Current", "In progress", "Attention required",
      "Blocked", "Completed", "Stale", "Skipped with rationale",
    ]);

    const systematic = deriveWorkflowStages(authority(), {
      "intent-contract-1": "completed",
      "task-center-1": "attention-required",
      "audit-lineage-1": "current",
    });
    expect(systematic[1]).toMatchObject({ state: "attention-required", stateLabel: "Attention required", optional: true });

    const revisitable = deriveWorkflowStages(authority("manuscript-review-revision"));
    expect(revisitable.map(({ stageKey }) => stageKey)).toEqual([
      "intent-contract-1", "manuscript-studio-1", "manuscript-studio-2", "audit-lineage-1",
    ]);
    expect(revisitable.every(({ processForm }) => processForm === "revisitable")).toBe(true);
    expect(revisitable.filter(({ pageContractId }) => pageContractId === "manuscript-studio.html").map(({ stageKey }) => stageKey)).toEqual([
      "manuscript-studio-1", "manuscript-studio-2",
    ]);
  });

  it("classifies workspaces relative to the selected profile and binds exact supporting return identity", () => {
    const systematic = authority("systematic-review");
    const theory = authority("theory-synthesis");
    expect(theory).toMatchObject({
      referenceId: catalog.referenceId,
      referenceVersion: catalog.referenceVersion,
      intentGuidanceVersion: catalog.intentGuidanceVersion,
      intentGuidanceHash: catalog.intentGuidanceHash,
    });
    expect(workspaceClassification(systematic, "tasks")).toMatchObject({ role: "primary", stageKeys: ["task-center-1"] });
    expect(workspaceClassification(theory, "tasks")).toMatchObject({ role: "supporting", stageKeys: [] });

    const support = createSupportingReturn(theory, "tasks");
    expect(support).not.toBeNull();
    expect(supportingReturnMatches(support!, theory)).toBe(true);

    const substitutions: WorkflowAuthoritySnapshot[] = [
      { ...theory, projectId: "22222222-2222-4222-8222-222222222222" },
      { ...theory, intentRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d042" },
      { ...theory, intentRevisionContentHash: `sha256:${"d".repeat(64)}` },
      { ...theory, profileCatalogHash: `sha256:${"e".repeat(64)}` },
      { ...theory, referenceId: "RO-UI-ACADEMIC-MINIMAL-1.6" },
      { ...theory, referenceVersion: "1.6" },
      { ...theory, intentGuidanceVersion: "1.1.0" },
      { ...theory, intentGuidanceHash: `sha256:${"f".repeat(64)}` },
      { ...theory, profileId: "systematic-review" },
      { ...theory, currentStageKey: "audit-lineage-1" },
      { ...theory, currentPageContractId: "audit-lineage.html" },
    ];
    for (const substituted of substitutions) expect(supportingReturnMatches(support!, substituted)).toBe(false);
  });

  it("refuses to fabricate a workflow for an absent, mismatched, closed, or incompatible Intent context", () => {
    const project = {
      projectId: "11111111-1111-4111-8111-111111111111",
      root: "C:/Research/current-project",
      open: true,
      compatibilityState: "compatible" as const,
    };
    expect(createWorkflowAuthoritySnapshot(project, catalog, { projectId: project.projectId, current: null })).toBeNull();
    expect(createWorkflowAuthoritySnapshot(project, catalog, { ...authorityIntent(), projectId: "other-project" })).toBeNull();
    expect(createWorkflowAuthoritySnapshot({ ...project, open: false }, catalog, authorityIntent())).toBeNull();
    expect(createWorkflowAuthoritySnapshot({ ...project, compatibilityState: "migration-required" }, catalog, authorityIntent())).toBeNull();
  });

  it("installs only the latest coherent project, Intent, and catalog response", async () => {
    const loader = new WorkflowContextLoader();
    const pending = new Map<string, (value: ReturnType<typeof authorityIntent>) => void>();
    const client = {
      workflowProfileCatalog: async () => catalog,
      workflowProgress: async ({ root }: { readonly root: string }) => workflowProgress(
        root === "C:/Research/project-b"
          ? "22222222-2222-4222-8222-222222222222"
          : "11111111-1111-4111-8111-111111111111",
      ),
      intent: async ({ root }: { readonly root: string }) => await new Promise<ReturnType<typeof authorityIntent>>((resolve) => {
        pending.set(root, resolve);
      }),
    };
    const projectA = {
      projectId: "11111111-1111-4111-8111-111111111111",
      root: "C:/Research/project-a",
      open: true,
      compatibilityState: "compatible" as const,
    };
    const projectB = {
      projectId: "22222222-2222-4222-8222-222222222222",
      root: "C:/Research/project-b",
      open: true,
      compatibilityState: "compatible" as const,
    };

    const loadingA = loader.load(projectA, client);
    const loadingB = loader.load(projectB, client);
    pending.get(projectB.root)?.({
      ...authorityIntent(),
      projectId: projectB.projectId,
    });
    await expect(loadingB).resolves.toMatchObject({ kind: "ready", authority: { projectId: projectB.projectId } });

    pending.get(projectA.root)?.(authorityIntent());
    await expect(loadingA).resolves.toEqual({ kind: "stale" });

    const mismatched = loader.load(projectA, {
      ...client,
      intent: async () => ({ ...authorityIntent(), projectId: projectB.projectId }),
    });
    await expect(mismatched).resolves.toMatchObject({ kind: "unavailable", reason: "incoherent" });
    loader.invalidate();
    await expect(loader.load(projectA, {
      ...client,
      intent: async () => { throw new Error("transport detail must not reach the shell"); },
    })).resolves.toEqual({
      kind: "error",
      message: "Guided workflow could not be loaded from the local Core service. The previous workflow context was cleared.",
    });
  });
});

function authorityIntent() {
  return {
    projectId: "11111111-1111-4111-8111-111111111111",
    current: {
      revisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d041",
      revisionContentHash: `sha256:${"c".repeat(64)}`,
      primaryUseCase: "systematic-review" as const,
    },
  };
}

function workflowProgress(projectId: string): WorkflowProgressProjection {
  return {
    schemaVersion: "1.0",
    projectId,
    selectionRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d051",
    selectionRevisionContentHash: `sha256:${"d".repeat(64)}`,
    profileId: "systematic-review",
    profileTitle: "Systematic review",
    processForm: "linear",
    bootstrapRequired: true,
    current: null,
    recommendedStageKey: "intent-contract-1",
    recommendedPageContractId: "intent-contract.html",
    recommendedAction: "Start the guided workflow.",
    checkpointState: "unknown",
    checkpointRationale,
    supportingHandoff: null,
    staleOutputs: [],
    history: [],
  };
}
