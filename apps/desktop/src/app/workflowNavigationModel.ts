import type {
  WorkflowProfileCatalogProjection,
  WorkflowProgressProjection,
  WorkflowProfileProjection,
  WorkflowProfileStageProjection,
} from "@research-observatory/contracts/core-api";

export const IMPLEMENTED_WORKSPACES = Object.freeze([
  { id: "projects", label: "Local projects", pageContractIds: ["projects.html", "new-project.html"] },
  { id: "home", label: "Project home", pageContractIds: ["index.html"] },
  { id: "intent", label: "Research intent", pageContractIds: ["intent-contract.html"] },
  { id: "tasks", label: "Task Center", pageContractIds: ["task-center.html"] },
  { id: "audit", label: "Audit & lineage", pageContractIds: ["audit-lineage.html"] },
  { id: "settings", label: "Project settings", pageContractIds: ["project-settings.html"] },
  { id: "application-settings", label: "Application settings", pageContractIds: ["application-settings.html"] },
  { id: "diagnostics", label: "Diagnostics & support", pageContractIds: ["help-onboarding.html"] },
] as const);

export type ApplicationWorkspace = (typeof IMPLEMENTED_WORKSPACES)[number]["id"];
export type WorkflowProfileId = WorkflowProfileProjection["profileId"];

export type WorkflowStageAuthorityState =
  | "not-started"
  | "available"
  | "current"
  | "in-progress"
  | "attention-required"
  | "blocked"
  | "completed"
  | "stale"
  | "skipped-with-rationale";

export type WorkflowStageDisplayState = WorkflowStageAuthorityState | "upcoming";

export interface WorkflowProjectIdentity {
  readonly projectId: string;
  readonly root: string;
  readonly open: boolean;
  readonly compatibilityState: "compatible" | "migration-required" | "newer-unsupported";
}

export interface WorkflowIntentSelection {
  readonly projectId: string;
  readonly current: {
    readonly revisionId: string;
    readonly revisionContentHash: string;
    readonly primaryUseCase: WorkflowProfileId;
  } | null;
}

export interface WorkflowAuthoritySnapshot {
  readonly projectId: string;
  readonly projectRoot: string;
  readonly intentRevisionId: string;
  readonly intentRevisionContentHash: string;
  readonly profileCatalogHash: string;
  readonly profileCatalogVersion: string;
  readonly referenceId: string;
  readonly referenceVersion: string;
  readonly intentGuidanceVersion: string;
  readonly intentGuidanceHash: string;
  readonly profileId: WorkflowProfileId;
  readonly profile: WorkflowProfileProjection;
  readonly currentStageKey: string;
  readonly currentPageContractId: string;
}

export interface WorkflowStageDisplay extends WorkflowProfileStageProjection {
  readonly state: WorkflowStageDisplayState;
  readonly stateLabel: string;
  readonly processForm: WorkflowProfileProjection["processForm"];
  readonly implementedWorkspace: ApplicationWorkspace | null;
}

export interface WorkspaceClassification {
  readonly role: "primary" | "supporting";
  readonly stageKeys: readonly string[];
  readonly pageContractIds: readonly string[];
}

export interface SupportingReturnContext {
  readonly supportingWorkspace: ApplicationWorkspace;
  readonly projectId: string;
  readonly projectRoot: string;
  readonly intentRevisionId: string;
  readonly intentRevisionContentHash: string;
  readonly profileCatalogHash: string;
  readonly profileCatalogVersion: string;
  readonly referenceId: string;
  readonly referenceVersion: string;
  readonly intentGuidanceVersion: string;
  readonly intentGuidanceHash: string;
  readonly profileId: WorkflowProfileId;
  readonly currentStageKey: string;
  readonly currentPageContractId: string;
}

export interface WorkflowContextClient<TIntent extends WorkflowIntentSelection = WorkflowIntentSelection> {
  workflowProfileCatalog(): Promise<WorkflowProfileCatalogProjection>;
  intent(command: { readonly root: string }): Promise<TIntent>;
  workflowProgress(command: { readonly root: string }): Promise<WorkflowProgressProjection>;
}

export type WorkflowContextLoadResult<TIntent extends WorkflowIntentSelection = WorkflowIntentSelection> =
  | {
      readonly kind: "ready";
      readonly authority: WorkflowAuthoritySnapshot;
      readonly catalog: WorkflowProfileCatalogProjection;
      readonly intent: TIntent;
      readonly progress: WorkflowProgressProjection;
    }
  | { readonly kind: "unavailable"; readonly reason: "project-unavailable" | "no-current-intent" | "incoherent" }
  | { readonly kind: "error"; readonly message: string }
  | { readonly kind: "stale" };

export class WorkflowContextLoader {
  private generation = 0;

  invalidate(): void {
    this.generation += 1;
  }

  async load<TIntent extends WorkflowIntentSelection>(
    project: WorkflowProjectIdentity,
    client: WorkflowContextClient<TIntent>,
  ): Promise<WorkflowContextLoadResult<TIntent>> {
    const generation = ++this.generation;
    if (!project.open || project.compatibilityState !== "compatible") {
      return { kind: "unavailable", reason: "project-unavailable" };
    }
    try {
      const [catalog, intent, progress] = await Promise.all([
        client.workflowProfileCatalog(),
        client.intent({ root: project.root }),
        client.workflowProgress({ root: project.root }),
      ]);
      if (generation !== this.generation) return { kind: "stale" };
      const progressCoherent = progress.projectId === project.projectId
        && progress.profileId === intent.current?.primaryUseCase
        && progress.processForm === catalog.profiles.find(({ profileId }) => profileId === progress.profileId)?.processForm;
      const authority = progressCoherent
        ? createWorkflowAuthoritySnapshot(
            project,
            catalog,
            intent,
            progress.current?.stageKey ?? progress.recommendedStageKey,
          )
        : null;
      if (authority) return { kind: "ready", authority, catalog, intent, progress };
      return {
        kind: "unavailable",
        reason: intent.projectId === project.projectId && intent.current === null
          ? "no-current-intent"
          : "incoherent",
      };
    } catch {
      if (generation !== this.generation) return { kind: "stale" };
      return {
        kind: "error",
        message: "Guided workflow could not be loaded from the local Core service. The previous workflow context was cleared.",
      };
    }
  }
}

export function implementedWorkspace(workspace: ApplicationWorkspace) {
  return IMPLEMENTED_WORKSPACES.find((candidate) => candidate.id === workspace)!;
}

export function implementedWorkspaceForStage(
  stage: Pick<WorkflowProfileStageProjection, "pageContractId">,
): ApplicationWorkspace | null {
  return IMPLEMENTED_WORKSPACES.find(({ pageContractIds }) => (
    (pageContractIds as readonly string[]).includes(stage.pageContractId)
  ))?.id ?? null;
}

export function createWorkflowAuthoritySnapshot(
  project: WorkflowProjectIdentity | null,
  catalog: WorkflowProfileCatalogProjection | null,
  intent: WorkflowIntentSelection | null,
  requestedStageKey?: string | null,
): WorkflowAuthoritySnapshot | null {
  if (!project || !project.open || project.compatibilityState !== "compatible" || !catalog || !intent?.current) return null;
  if (intent.projectId !== project.projectId) return null;
  const profile = catalog.profiles.find(({ profileId }) => profileId === intent.current?.primaryUseCase);
  if (!profile) return null;
  const requested = requestedStageKey
    ? profile.stages.find(({ stageKey }) => stageKey === requestedStageKey)
    : null;
  const current = requested ?? profile.stages[0];
  if (!current) return null;
  return Object.freeze({
    projectId: project.projectId,
    projectRoot: project.root,
    intentRevisionId: intent.current.revisionId,
    intentRevisionContentHash: intent.current.revisionContentHash,
    profileCatalogHash: catalog.profileCatalogHash,
    profileCatalogVersion: catalog.profileCatalogVersion,
    referenceId: catalog.referenceId,
    referenceVersion: catalog.referenceVersion,
    intentGuidanceVersion: catalog.intentGuidanceVersion,
    intentGuidanceHash: catalog.intentGuidanceHash,
    profileId: profile.profileId,
    profile,
    currentStageKey: current.stageKey,
    currentPageContractId: current.pageContractId,
  });
}

export function stageDisplayLabel(state: WorkflowStageAuthorityState): string {
  switch (state) {
    case "not-started": return "Not started";
    case "available": return "Available";
    case "current": return "Current";
    case "in-progress": return "In progress";
    case "attention-required": return "Attention required";
    case "blocked": return "Blocked";
    case "completed": return "Completed";
    case "stale": return "Stale";
    case "skipped-with-rationale": return "Skipped with rationale";
  }
}

function displayLabel(state: WorkflowStageDisplayState): string {
  return state === "upcoming" ? "Upcoming" : stageDisplayLabel(state);
}

export function deriveWorkflowStages(
  authority: WorkflowAuthoritySnapshot,
  authoritativeStates: Readonly<Partial<Record<string, WorkflowStageAuthorityState>>> = {},
): readonly WorkflowStageDisplay[] {
  return authority.profile.stages.map((stage) => {
    const state = authoritativeStates[stage.stageKey]
      ?? (stage.stageKey === authority.currentStageKey ? "current" : "upcoming");
    return Object.freeze({
      ...stage,
      state,
      stateLabel: displayLabel(state),
      processForm: authority.profile.processForm,
      implementedWorkspace: implementedWorkspaceForStage(stage),
    });
  });
}

export function workspaceClassification(
  authority: WorkflowAuthoritySnapshot,
  workspace: ApplicationWorkspace,
): WorkspaceClassification {
  const definition = implementedWorkspace(workspace);
  const stages = authority.profile.stages.filter(({ pageContractId }) => (
    (definition.pageContractIds as readonly string[]).includes(pageContractId)
  ));
  return Object.freeze({
    role: stages.length > 0 ? "primary" : "supporting",
    stageKeys: Object.freeze(stages.map(({ stageKey }) => stageKey)),
    pageContractIds: definition.pageContractIds,
  });
}

export function selectPrimaryStage(
  authority: WorkflowAuthoritySnapshot,
  stageKey: string,
): { readonly authority: WorkflowAuthoritySnapshot; readonly workspace: ApplicationWorkspace | null } | null {
  const stage = authority.profile.stages.find((candidate) => candidate.stageKey === stageKey);
  if (!stage) return null;
  return Object.freeze({
    authority: Object.freeze({
      ...authority,
      currentStageKey: stage.stageKey,
      currentPageContractId: stage.pageContractId,
    }),
    workspace: implementedWorkspaceForStage(stage),
  });
}

export function createSupportingReturn(
  authority: WorkflowAuthoritySnapshot,
  supportingWorkspace: ApplicationWorkspace,
): SupportingReturnContext | null {
  if (workspaceClassification(authority, supportingWorkspace).role !== "supporting") return null;
  return Object.freeze({
    supportingWorkspace,
    projectId: authority.projectId,
    projectRoot: authority.projectRoot,
    intentRevisionId: authority.intentRevisionId,
    intentRevisionContentHash: authority.intentRevisionContentHash,
    profileCatalogHash: authority.profileCatalogHash,
    profileCatalogVersion: authority.profileCatalogVersion,
    referenceId: authority.referenceId,
    referenceVersion: authority.referenceVersion,
    intentGuidanceVersion: authority.intentGuidanceVersion,
    intentGuidanceHash: authority.intentGuidanceHash,
    profileId: authority.profileId,
    currentStageKey: authority.currentStageKey,
    currentPageContractId: authority.currentPageContractId,
  });
}

export function supportingReturnMatches(
  context: SupportingReturnContext,
  authority: WorkflowAuthoritySnapshot | null,
): boolean {
  return authority !== null
    && context.projectId === authority.projectId
    && context.projectRoot === authority.projectRoot
    && context.intentRevisionId === authority.intentRevisionId
    && context.intentRevisionContentHash === authority.intentRevisionContentHash
    && context.profileCatalogHash === authority.profileCatalogHash
    && context.profileCatalogVersion === authority.profileCatalogVersion
    && context.referenceId === authority.referenceId
    && context.referenceVersion === authority.referenceVersion
    && context.intentGuidanceVersion === authority.intentGuidanceVersion
    && context.intentGuidanceHash === authority.intentGuidanceHash
    && context.profileId === authority.profileId
    && context.currentStageKey === authority.currentStageKey
    && context.currentPageContractId === authority.currentPageContractId;
}
