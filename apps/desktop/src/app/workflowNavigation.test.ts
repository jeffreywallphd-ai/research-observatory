import { describe, expect, it } from "vitest";

import type {
  WorkflowProfileCatalogProjection,
  WorkflowProgressProjection,
} from "@research-observatory/contracts/core-api";

import {
  IMPLEMENTED_WORKSPACES,
  WorkflowContextLoader,
  WorkflowRequestGuard,
  createSupportingReturn,
  createWorkflowAuthoritySnapshot,
  deriveWorkflowStages,
  selectPrimaryStage,
  stageDisplayLabel,
  supportingReturnMatches,
  workflowCommandStageAuthority,
  workflowRevisitSources,
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

    const progress = activeWorkflowProgress(theory, "task-center.html");
    const support = createSupportingReturn(theory, "tasks", progress);
    expect(support).not.toBeNull();
    expect(supportingReturnMatches(support!, theory, progress)).toBe(true);

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
    for (const substituted of substitutions) expect(supportingReturnMatches(support!, substituted, progress)).toBe(false);
    expect(createSupportingReturn(theory, "tasks", { ...progress, supportingHandoff: null })).toBeNull();
    expect(supportingReturnMatches(support!, theory, { ...progress, supportingHandoff: null })).toBe(false);
    expect(supportingReturnMatches(support!, theory, {
      ...progress,
      supportingHandoff: {
        ...progress.supportingHandoff!,
        stageStateRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d099",
      },
    })).toBe(false);
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
    for (const substituted of [
      { intentRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d099" },
      { intentRevisionContentHash: `sha256:${"9".repeat(64)}` },
    ]) {
      await expect(loader.load(projectA, {
        ...client,
        intent: async () => authorityIntent(),
        workflowProgress: async () => ({ ...workflowProgress(projectA.projectId), ...substituted }),
      })).resolves.toMatchObject({ kind: "unavailable", reason: "incoherent" });
    }
    loader.invalidate();
    await expect(loader.load(projectA, {
      ...client,
      intent: async () => { throw new Error("transport detail must not reach the shell"); },
    })).resolves.toEqual({
      kind: "error",
      message: "Guided workflow could not be loaded from the local Core service. The previous workflow context was cleared.",
    });
  });

  it("discards delayed start, revisit, and supporting successes after project B becomes current", async () => {
    const projectA = workflowProject("a");
    const projectB = workflowProject("b");
    const applied: string[] = [];
    for (const kind of ["start", "resume", "revisit", "open-supporting"] as const) {
      const guard = new WorkflowRequestGuard();
      const progressA = kind === "start"
        ? workflowProgress(projectA.projectId)
        : activeWorkflowProgress(authority(), "task-center.html");
      const ticket = guard.begin(kind, projectA, progressA, kind === "start" ? null : progressA.current);
      expect(ticket).not.toBeNull();
      let release!: (value: WorkflowProgressProjection) => void;
      const delayed = new Promise<WorkflowProgressProjection>((resolve) => { release = resolve; });
      const completion = delayed.then((result) => {
        if (guard.acceptsResult(ticket!, projectB, workflowProgress(projectB.projectId), result)) {
          applied.push(`${kind}:${result.projectId}`);
        }
      });

      guard.invalidate();
      release(progressA);
      await completion;

      expect(guard.owns(ticket!, projectB)).toBe(false);
      expect(guard.matchesSource(ticket!, projectB, workflowProgress(projectB.projectId))).toBe(false);
    }
    expect(applied).toEqual([]);
  });

  it("discards delayed workflow errors, finally, announcements, and returns after A to B to A", async () => {
    const projectA = workflowProject("a");
    const effects: string[] = [];
    for (const kind of ["start", "resume", "revisit", "open-supporting"] as const) {
      const guard = new WorkflowRequestGuard();
      const progressA = kind === "start"
        ? workflowProgress(projectA.projectId)
        : activeWorkflowProgress(authority(), "task-center.html");
      const ticket = guard.begin(kind, projectA, progressA, kind === "start" ? null : progressA.current);
      expect(ticket).not.toBeNull();
      let release!: () => void;
      const delayed = new Promise<void>((resolve) => { release = resolve; });
      const completion = delayed.then(() => {
        if (guard.matchesSource(ticket!, projectA, progressA)) effects.push(`${kind}:error`, `${kind}:announcement`);
        if (guard.owns(ticket!, projectA)) effects.push(`${kind}:finally`, `${kind}:return-context`);
      });

      guard.invalidate(); // A -> B
      guard.invalidate(); // B -> A with the same exact persisted authority
      release();
      await completion;

      expect(guard.owns(ticket!, projectA)).toBe(false);
    }
    expect(effects).toEqual([]);
  });

  it("cancels a selected terminal-source revisit after A to B to A context replacement", async () => {
    const projectA = workflowProject("a");
    const base = activeWorkflowProgress(authority("manuscript-review-revision"), "task-center.html");
    const active = {
      ...base.current!,
      stageKey: "manuscript-studio-1",
      pageContractId: "manuscript-studio.html",
    };
    const source = {
      ...base.current!,
      stageStateId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d080",
      stageStateRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d081",
      revision: 2,
      revisionContentHash: `sha256:${"7".repeat(64)}`,
      status: "completed" as const,
    };
    const progress = {
      ...base,
      current: active,
      recommendedStageKey: active.stageKey,
      recommendedPageContractId: active.pageContractId,
      history: [source],
    };
    const commandAuthority = workflowCommandStageAuthority("revisit", progress, source);
    expect(commandAuthority?.sourceStage).toEqual(source);
    const guard = new WorkflowRequestGuard();
    const ticket = guard.begin("revisit", projectA, progress, commandAuthority!.sourceStage);
    expect(ticket).not.toBeNull();
    guard.invalidate();
    guard.invalidate();
    expect(guard.matchesSource(ticket!, projectA, progress)).toBe(false);
    expect(guard.acceptsResult(ticket!, projectA, progress, {
      ...progress,
      current: { ...source, status: "current", passNumber: source.passNumber + 1 },
    })).toBe(false);
  });

  it("binds request ownership to exact root, Intent, selection, and active/source heads", () => {
    const guard = new WorkflowRequestGuard();
    const project = workflowProject("a");
    const progress = activeWorkflowProgress(authority(), "task-center.html");
    const ticket = guard.begin("revisit", project, progress, progress.current);
    expect(ticket).not.toBeNull();
    expect(guard.matchesSource(ticket!, project, progress)).toBe(true);
    expect(guard.owns(ticket!, { ...project, root: "C:/Research/substituted" })).toBe(false);
    expect(guard.matchesSource(ticket!, project, {
      ...progress,
      selectionRevisionContentHash: `sha256:${"8".repeat(64)}`,
    })).toBe(false);
    expect(guard.matchesSource(ticket!, project, {
      ...progress,
      current: { ...progress.current!, stageStateRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d099" },
    })).toBe(false);
    const substitutedIntent: IntentBoundProgress = {
      ...progress,
      intentRevisionContentHash: `sha256:${"7".repeat(64)}`,
    };
    expect(guard.acceptsResult(ticket!, project, progress, substitutedIntent)).toBe(false);
  });

  it("binds revisit source separately from the active displaced-head CAS", () => {
    const base = activeWorkflowProgress(authority("manuscript-review-revision"), "task-center.html");
    const progress = {
      ...base,
      current: {
        ...base.current!,
        stageKey: "manuscript-studio-1",
        pageContractId: "manuscript-studio.html",
      },
      recommendedStageKey: "manuscript-studio-1",
      recommendedPageContractId: "manuscript-studio.html",
    };
    const source = {
      ...base.current!,
      completionEvidenceIds: ["018f47a2-4d6b-7f78-9f2e-7fb76c86d082"],
      revision: 2,
      revisionContentHash: `sha256:${"7".repeat(64)}`,
      stageStateId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d080",
      stageStateRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d081",
      status: "completed" as const,
    };
    const earlierStageProjection = {
      ...progress,
      history: [source],
    };
    const revisiting = workflowCommandStageAuthority("revisit", earlierStageProjection, source);
    expect(revisiting).toMatchObject({
      stageKey: source.stageKey,
      expectedStageStateRevisionId: progress.current!.stageStateRevisionId,
      expectedStageStateRevisionContentHash: progress.current!.revisionContentHash,
      revisitSourceStageStateRevisionId: source.stageStateRevisionId,
      revisitSourceStageStateRevisionContentHash: source.revisionContentHash,
    });
    expect(workflowRevisitSources(earlierStageProjection)).toEqual([source]);
    expect(workflowCommandStageAuthority("revisit", earlierStageProjection)).toBeNull();

    expect(workflowCommandStageAuthority("revisit", {
      ...progress,
      current: null,
      supportingHandoff: null,
      recommendedStageKey: source.stageKey,
      history: [source],
    })).toMatchObject({
      expectedStageStateRevisionId: null,
      expectedStageStateRevisionContentHash: null,
      revisitSourceStageStateRevisionId: source.stageStateRevisionId,
      revisitSourceStageStateRevisionContentHash: source.revisionContentHash,
    });
    expect(workflowCommandStageAuthority("revisit", {
      ...progress,
      history: [{ ...source, status: "current" }],
    })).toBeNull();
    expect(workflowCommandStageAuthority("revisit", {
      ...earlierStageProjection,
      processForm: "linear",
    }, source)).toBeNull();
    expect(workflowCommandStageAuthority("revisit", earlierStageProjection, {
      ...source,
      stageStateRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d099",
    })).toBeNull();
    expect(workflowCommandStageAuthority("start", workflowProgress(progress.projectId))).toMatchObject({
      revisitSourceStageStateRevisionId: null,
      revisitSourceStageStateRevisionContentHash: null,
    });
    const attention = {
      ...progress,
      current: {
        ...progress.current!,
        status: "attention-required" as const,
        attentionReason: "Researcher review is required before continuing.",
      },
    };
    expect(workflowCommandStageAuthority("resume", attention)).toMatchObject({
      stageKey: attention.current.stageKey,
      expectedStageStateRevisionId: attention.current.stageStateRevisionId,
      expectedStageStateRevisionContentHash: attention.current.revisionContentHash,
      revisitSourceStageStateRevisionId: null,
      revisitSourceStageStateRevisionContentHash: null,
      sourceStage: null,
    });
    expect(workflowCommandStageAuthority("resume", progress)).toBeNull();
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

function workflowProject(suffix: "a" | "b") {
  return {
    projectId: suffix === "a"
      ? "11111111-1111-4111-8111-111111111111"
      : "22222222-2222-4222-8222-222222222222",
    root: `C:/Research/project-${suffix}`,
    open: true,
    compatibilityState: "compatible" as const,
  };
}

type IntentBoundProgress = WorkflowProgressProjection & {
  readonly intentRevisionId: string;
  readonly intentRevisionContentHash: string;
};

function workflowProgress(projectId: string): IntentBoundProgress {
  return {
    schemaVersion: "1.0",
    projectId,
    intentRevisionId: authorityIntent().current.revisionId,
    intentRevisionContentHash: authorityIntent().current.revisionContentHash,
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

function activeWorkflowProgress(
  selected: WorkflowAuthoritySnapshot,
  supportingPageContractId: string,
): IntentBoundProgress {
  const primary = {
    attentionReason: null,
    completionEvidenceIds: [],
    navigationRole: "primary" as const,
    pageContractId: selected.currentPageContractId,
    parentStateRevisionId: null,
    passNumber: 1,
    revision: 1,
    revisionContentHash: `sha256:${"4".repeat(64)}`,
    skipRationale: null,
    stageKey: selected.currentStageKey,
    stageStateId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d061",
    stageStateRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d062",
    staleCauseIds: [],
    status: "current" as const,
    updatedAt: "2026-09-03T12:00:00.000Z",
  };
  return {
    ...workflowProgress(selected.projectId),
    intentRevisionId: selected.intentRevisionId,
    intentRevisionContentHash: selected.intentRevisionContentHash,
    profileId: selected.profileId,
    profileTitle: selected.profile.title,
    processForm: selected.profile.processForm,
    bootstrapRequired: false,
    current: primary,
    recommendedStageKey: selected.currentStageKey,
    recommendedPageContractId: selected.currentPageContractId,
    supportingHandoff: {
      navigationRole: "supporting",
      pageContractId: supportingPageContractId,
      returnStageStateRevisionId: primary.stageStateRevisionId,
      revisionContentHash: `sha256:${"5".repeat(64)}`,
      stageStateId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d071",
      stageStateRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d072",
    },
  };
}
