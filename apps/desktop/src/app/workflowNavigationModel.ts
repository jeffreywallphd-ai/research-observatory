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
  readonly selectionRevisionId: string;
  readonly selectionRevisionContentHash: string;
  readonly stageStateId: string;
  readonly stageStateRevisionId: string;
  readonly stageStateRevisionContentHash: string;
  readonly returnStageStateRevisionId: string;
  readonly supportingPageContractId: string;
}

type WorkflowProgressIntentWitness = WorkflowProgressProjection & {
  readonly intentRevisionId?: unknown;
  readonly intentRevisionContentHash?: unknown;
};

export type WorkflowProgressStage = NonNullable<WorkflowProgressProjection["current"]>;

export type WorkflowRequestKind = "start" | "resume" | "revisit" | "open-supporting";

export interface WorkflowRequestTicket {
  readonly kind: WorkflowRequestKind;
  readonly contextGeneration: number;
  readonly requestGeneration: number;
  readonly projectId: string;
  readonly projectRoot: string;
  readonly intentRevisionId: string;
  readonly intentRevisionContentHash: string;
  readonly selectionRevisionId: string;
  readonly selectionRevisionContentHash: string;
  readonly profileId: WorkflowProfileId;
  readonly activeStageStateRevisionId: string | null;
  readonly activeStageStateRevisionContentHash: string | null;
  readonly sourceStageStateRevisionId: string | null;
  readonly sourceStageStateRevisionContentHash: string | null;
}

export interface WorkflowCommandStageAuthority {
  readonly stageKey: string;
  readonly expectedStageStateRevisionId: string | null;
  readonly expectedStageStateRevisionContentHash: string | null;
  readonly revisitSourceStageStateRevisionId: string | null;
  readonly revisitSourceStageStateRevisionContentHash: string | null;
  readonly sourceStage: WorkflowProgressStage | null;
}

const REVISITABLE_SOURCE_STATES = new Set<WorkflowProgressStage["status"]>([
  "completed",
  "skipped-with-rationale",
  "stale",
]);

export function workflowRevisitSources(
  progress: WorkflowProgressProjection,
): readonly WorkflowProgressStage[] {
  if (progress.processForm !== "revisitable") return [];
  const seenAggregates = new Set<string>();
  const sources: WorkflowProgressStage[] = [];
  const candidates = progress.current === null
    ? progress.history
    : [progress.current, ...progress.history];
  for (const stage of candidates) {
    if (stage.navigationRole !== "primary" || seenAggregates.has(stage.stageStateId)) continue;
    seenAggregates.add(stage.stageStateId);
    if (REVISITABLE_SOURCE_STATES.has(stage.status)) sources.push(stage);
  }
  return Object.freeze(sources);
}

export function workflowCommandStageAuthority(
  action: "start" | "resume" | "revisit",
  progress: WorkflowProgressProjection,
  selectedRevisitSource: WorkflowProgressStage | null = null,
): WorkflowCommandStageAuthority | null {
  const active = progress.current;
  if (action === "start") {
    return Object.freeze({
      stageKey: progress.recommendedStageKey,
      expectedStageStateRevisionId: active?.stageStateRevisionId ?? null,
      expectedStageStateRevisionContentHash: active?.revisionContentHash ?? null,
      revisitSourceStageStateRevisionId: null,
      revisitSourceStageStateRevisionContentHash: null,
      sourceStage: null,
    });
  }
  if (action === "resume") {
    if (!active || !new Set<WorkflowProgressStage["status"]>(["attention-required", "blocked"]).has(active.status)) {
      return null;
    }
    return Object.freeze({
      stageKey: active.stageKey,
      expectedStageStateRevisionId: active.stageStateRevisionId,
      expectedStageStateRevisionContentHash: active.revisionContentHash,
      revisitSourceStageStateRevisionId: null,
      revisitSourceStageStateRevisionContentHash: null,
      sourceStage: null,
    });
  }
  const sources = workflowRevisitSources(progress);
  const source = selectedRevisitSource === null
    ? sources.find((stage) => stage.stageKey === progress.recommendedStageKey) ?? null
    : sources.find((stage) => (
      stage.stageKey === selectedRevisitSource.stageKey
      && stage.stageStateId === selectedRevisitSource.stageStateId
      && stage.stageStateRevisionId === selectedRevisitSource.stageStateRevisionId
      && stage.revisionContentHash === selectedRevisitSource.revisionContentHash
    )) ?? null;
  if (!source) return null;
  return Object.freeze({
    stageKey: source.stageKey,
    expectedStageStateRevisionId: active?.stageStateRevisionId ?? null,
    expectedStageStateRevisionContentHash: active?.revisionContentHash ?? null,
    revisitSourceStageStateRevisionId: source.stageStateRevisionId,
    revisitSourceStageStateRevisionContentHash: source.revisionContentHash,
    sourceStage: source,
  });
}

function progressIntentWitness(progress: WorkflowProgressProjection): {
  readonly revisionId: string;
  readonly revisionContentHash: string;
} | null {
  const witness = progress as WorkflowProgressIntentWitness;
  return typeof witness.intentRevisionId === "string"
    && typeof witness.intentRevisionContentHash === "string"
    ? {
        revisionId: witness.intentRevisionId,
        revisionContentHash: witness.intentRevisionContentHash,
      }
    : null;
}

function sameStageRevision(
  stage: WorkflowProgressStage | null,
  revisionId: string | null,
  revisionContentHash: string | null,
): boolean {
  return (stage?.stageStateRevisionId ?? null) === revisionId
    && (stage?.revisionContentHash ?? null) === revisionContentHash;
}

function requestSource(
  kind: WorkflowRequestKind,
  contextGeneration: number,
  requestGeneration: number,
  project: WorkflowProjectIdentity,
  progress: WorkflowProgressProjection,
  sourceStage: WorkflowProgressStage | null,
): WorkflowRequestTicket | null {
  const intent = progressIntentWitness(progress);
  if (
    !intent
    || !project.open
    || project.compatibilityState !== "compatible"
    || progress.projectId !== project.projectId
  ) return null;
  return Object.freeze({
    kind,
    contextGeneration,
    requestGeneration,
    projectId: project.projectId,
    projectRoot: project.root,
    intentRevisionId: intent.revisionId,
    intentRevisionContentHash: intent.revisionContentHash,
    selectionRevisionId: progress.selectionRevisionId,
    selectionRevisionContentHash: progress.selectionRevisionContentHash,
    profileId: progress.profileId,
    activeStageStateRevisionId: progress.current?.stageStateRevisionId ?? null,
    activeStageStateRevisionContentHash: progress.current?.revisionContentHash ?? null,
    sourceStageStateRevisionId: sourceStage?.stageStateRevisionId ?? null,
    sourceStageStateRevisionContentHash: sourceStage?.revisionContentHash ?? null,
  });
}

/**
 * Owns renderer-side workflow requests without treating project identity as a
 * generation. Returning A -> B -> A therefore cannot revive an old A request.
 */
export class WorkflowRequestGuard {
  private contextGeneration = 0;
  private readonly requestGenerations: Record<WorkflowRequestKind, number> = {
    start: 0,
    resume: 0,
    revisit: 0,
    "open-supporting": 0,
  };

  invalidate(): void {
    this.contextGeneration += 1;
  }

  begin(
    kind: WorkflowRequestKind,
    project: WorkflowProjectIdentity,
    progress: WorkflowProgressProjection,
    sourceStage: WorkflowProgressStage | null,
  ): WorkflowRequestTicket | null {
    const requestGeneration = this.requestGenerations[kind] + 1;
    this.requestGenerations[kind] = requestGeneration;
    return requestSource(
      kind,
      this.contextGeneration,
      requestGeneration,
      project,
      progress,
      sourceStage,
    );
  }

  owns(ticket: WorkflowRequestTicket, project: WorkflowProjectIdentity | null): boolean {
    return project !== null
      && ticket.contextGeneration === this.contextGeneration
      && ticket.requestGeneration === this.requestGenerations[ticket.kind]
      && ticket.projectId === project.projectId
      && ticket.projectRoot === project.root
      && project.open
      && project.compatibilityState === "compatible";
  }

  matchesSource(
    ticket: WorkflowRequestTicket,
    project: WorkflowProjectIdentity | null,
    progress: WorkflowProgressProjection | null,
  ): boolean {
    if (!this.owns(ticket, project) || !progress) return false;
    const intent = progressIntentWitness(progress);
    const sourcePresent = ticket.sourceStageStateRevisionId === null
      || [progress.current, ...progress.history].some((stage) => sameStageRevision(
        stage,
        ticket.sourceStageStateRevisionId,
        ticket.sourceStageStateRevisionContentHash,
      ));
    return intent !== null
      && progress.projectId === ticket.projectId
      && intent.revisionId === ticket.intentRevisionId
      && intent.revisionContentHash === ticket.intentRevisionContentHash
      && progress.selectionRevisionId === ticket.selectionRevisionId
      && progress.selectionRevisionContentHash === ticket.selectionRevisionContentHash
      && progress.profileId === ticket.profileId
      && sameStageRevision(
        progress.current,
        ticket.activeStageStateRevisionId,
        ticket.activeStageStateRevisionContentHash,
      )
      && sourcePresent;
  }

  acceptsResult(
    ticket: WorkflowRequestTicket,
    project: WorkflowProjectIdentity | null,
    sourceProgress: WorkflowProgressProjection | null,
    result: WorkflowProgressProjection,
  ): boolean {
    if (!this.matchesSource(ticket, project, sourceProgress)) return false;
    const intent = progressIntentWitness(result);
    return intent !== null
      && result.projectId === ticket.projectId
      && intent.revisionId === ticket.intentRevisionId
      && intent.revisionContentHash === ticket.intentRevisionContentHash
      && result.selectionRevisionId === ticket.selectionRevisionId
      && result.selectionRevisionContentHash === ticket.selectionRevisionContentHash
      && result.profileId === ticket.profileId;
  }
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
      const progressIntent = progressIntentWitness(progress);
      const progressCoherent = intent.current !== null
        && progressIntent !== null
        && intent.projectId === project.projectId
        && progress.projectId === project.projectId
        && progressIntent.revisionId === intent.current.revisionId
        && progressIntent.revisionContentHash === intent.current.revisionContentHash
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
  progress: WorkflowProgressProjection,
): SupportingReturnContext | null {
  if (workspaceClassification(authority, supportingWorkspace).role !== "supporting") return null;
  const handoff = progress.supportingHandoff;
  const intent = progressIntentWitness(progress);
  const workspace = implementedWorkspace(supportingWorkspace);
  if (
    !handoff
    || handoff.navigationRole !== "supporting"
    || !(workspace.pageContractIds as readonly string[]).includes(handoff.pageContractId)
    || !progress.current
    || handoff.returnStageStateRevisionId !== progress.current.stageStateRevisionId
    || progress.current.stageKey !== authority.currentStageKey
    || progress.projectId !== authority.projectId
    || progress.profileId !== authority.profileId
    || !intent
    || intent.revisionId !== authority.intentRevisionId
    || intent.revisionContentHash !== authority.intentRevisionContentHash
  ) return null;
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
    selectionRevisionId: progress.selectionRevisionId,
    selectionRevisionContentHash: progress.selectionRevisionContentHash,
    stageStateId: handoff.stageStateId,
    stageStateRevisionId: handoff.stageStateRevisionId,
    stageStateRevisionContentHash: handoff.revisionContentHash,
    returnStageStateRevisionId: handoff.returnStageStateRevisionId,
    supportingPageContractId: handoff.pageContractId,
  });
}

export function supportingReturnMatches(
  context: SupportingReturnContext,
  authority: WorkflowAuthoritySnapshot | null,
  progress?: WorkflowProgressProjection | null,
): boolean {
  const progressIntent = progress ? progressIntentWitness(progress) : null;
  const handoff = progress?.supportingHandoff ?? null;
  const serverWitnessMatches = progress === undefined || (
    progress !== null
    && progressIntent !== null
    && progress.projectId === context.projectId
    && progressIntent.revisionId === context.intentRevisionId
    && progressIntent.revisionContentHash === context.intentRevisionContentHash
    && progress.profileId === context.profileId
    && progress.selectionRevisionId === context.selectionRevisionId
    && progress.selectionRevisionContentHash === context.selectionRevisionContentHash
    && progress.current?.stageKey === context.currentStageKey
    && progress.current.stageStateRevisionId === context.returnStageStateRevisionId
    && handoff !== null
    && handoff.navigationRole === "supporting"
    && handoff.stageStateId === context.stageStateId
    && handoff.stageStateRevisionId === context.stageStateRevisionId
    && handoff.revisionContentHash === context.stageStateRevisionContentHash
    && handoff.returnStageStateRevisionId === context.returnStageStateRevisionId
    && handoff.pageContractId === context.supportingPageContractId
  );
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
    && context.currentPageContractId === authority.currentPageContractId
    && serverWitnessMatches;
}
