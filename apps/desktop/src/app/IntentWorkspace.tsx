import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";

import {
  CoreApiClientError,
  createCoreApiClient,
  type CoreApiTransport,
  type IntentAcceptRequest,
  type IntentDraftProjection,
  type IntentDraftRequest,
  type IntentImpactPreview,
  type IntentWorkspaceProjection,
  type ProjectProjection,
  type WorkflowProfileCatalogProjection,
} from "@research-observatory/contracts/core-api";
import { Button, Notification, Panel, StatusBadge, Typography } from "@research-observatory/ui-components";

import { packagedProjectTransport } from "./ProjectsWorkspace";

type PrimaryUseCase = IntentDraftRequest["primaryUseCase"];
type EvidenceType = IntentDraftRequest["evidenceTypes"][number];
type NoveltyStandard = NonNullable<IntentDraftRequest["noveltyStandard"]>;
type WorkflowProfile = WorkflowProfileCatalogProjection["profiles"][number];
export type IntentProjectIdentity = Pick<ProjectProjection, "projectId" | "root">;

const EVIDENCE_TYPES: readonly EvidenceType[] = [
  "empirical-study", "systematic-review", "theoretical-work", "technical-evaluation", "standard",
  "dataset", "interpretive-text", "stakeholder-account", "critical-analysis", "private-report",
];

export function selectedIntentGuidance(
  catalog: WorkflowProfileCatalogProjection,
  useCase: PrimaryUseCase,
): WorkflowProfile {
  const guidance = catalog.profiles.find((candidate) => candidate.profileId === useCase);
  if (!guidance) throw new Error("RO-CORE-INTENT-MODE-INVALID");
  return guidance;
}

export function intentProfileSelectionDefaults(
  catalog: WorkflowProfileCatalogProjection,
  useCase: PrimaryUseCase,
): Pick<IntentFormState, "primaryUseCase" | "evidenceTypes" | "noveltyStandard" | "autonomyLevel" | "stoppingConditions"> {
  const profile = selectedIntentGuidance(catalog, useCase);
  return {
    primaryUseCase: profile.profileId,
    evidenceTypes: profile.defaultEvidenceTypes,
    noveltyStandard: profile.defaultNoveltyStandard,
    autonomyLevel: profile.defaultAutonomyLevel,
    stoppingConditions: profile.defaultStoppingConditions,
  };
}

export function intentWorkspaceAvailability(project: ProjectProjection | null): {
  readonly available: boolean;
  readonly state: "empty" | "offline" | "denied" | null;
  readonly message: string;
} {
  if (!project) return { available: false, state: "empty", message: "Open a compatible local project before defining research intent." };
  if (!project.open || project.accessMode === "closed") return { available: false, state: "offline", message: "The selected project is closed. Open it to load its research intent." };
  if (project.accessMode !== "read-write" || project.compatibilityState !== "compatible") return { available: false, state: "denied", message: "Research intent is read-only for this project. Keep the package unchanged and follow its backup-first recovery path." };
  return { available: true, state: null, message: "Research intent is available for this exclusive local project session." };
}

export function intentAcceptanceAvailability(current: IntentDraftProjection | null): {
  readonly available: boolean;
  readonly state: "empty" | "incomplete" | "ready" | "accepted";
  readonly message: string;
} {
  if (!current) return { available: false, state: "empty", message: "Save a decision-complete draft before requesting acceptance." };
  if (current.status === "accepted") return { available: false, state: "accepted", message: "This exact revision is accepted and may govern downstream policy checks." };
  if (!current.decisionComplete || !current.canRequestAcceptance) return { available: false, state: "incomplete", message: "Resolve every required intent decision before requesting human acceptance." };
  return { available: true, state: "ready", message: "Review and confirm this exact decision-complete draft before it can govern automation." };
}

export function intentAcceptanceRequest(
  root: string,
  current: IntentDraftProjection,
  decisionRationale: string,
): IntentAcceptRequest {
  return {
    root,
    expectedRevision: current.revision,
    expectedRevisionContentHash: current.revisionContentHash,
    confirmed: true,
    decisionRationale: decisionRationale.trim(),
  };
}

export interface IntentAcceptanceAttempt {
  readonly command: IntentAcceptRequest;
  readonly idempotencyKey: string;
  readonly revisionId: string;
}

type IntentAcceptanceClient = Pick<ReturnType<typeof createCoreApiClient>, "acceptIntent">;

export type IntentAcceptanceExecution =
  | { readonly status: "accepted"; readonly accepted: IntentDraftProjection; readonly attempt: IntentAcceptanceAttempt }
  | { readonly status: "rejected" | "unresolved"; readonly error: unknown; readonly attempt: IntentAcceptanceAttempt };

export class IntentAcceptanceCoordinator {
  private pending: IntentAcceptanceAttempt | null = null;

  constructor(
    private readonly client: IntentAcceptanceClient,
    private readonly createIdempotencyKey: () => string = idempotencyKey,
  ) {}

  pendingAttempt(): IntentAcceptanceAttempt | null {
    return this.pending;
  }

  prepare(root: string, current: IntentDraftProjection, decisionRationale: string): IntentAcceptanceAttempt {
    if (this.pending) return this.pending;
    this.pending = Object.freeze({
      command: Object.freeze(intentAcceptanceRequest(root, current, decisionRationale)),
      idempotencyKey: this.createIdempotencyKey(),
      revisionId: current.revisionId,
    });
    return this.pending;
  }

  reset(): void {
    this.pending = null;
  }

  async execute(): Promise<IntentAcceptanceExecution> {
    const attempt = this.pending;
    if (!attempt) throw new Error("RO-DESKTOP-INTENT-ACCEPTANCE-NOT-PREPARED");
    try {
      const accepted = await this.client.acceptIntent(attempt.command, attempt.idempotencyKey);
      this.pending = null;
      return { status: "accepted", accepted, attempt };
    } catch (error: unknown) {
      if (error instanceof CoreApiClientError) {
        this.pending = null;
        return { status: "rejected", error, attempt };
      }
      return { status: "unresolved", error, attempt };
    }
  }
}

export function acceptedIntentWorkspace(
  previous: IntentWorkspaceProjection | null,
  projectId: string,
  accepted: IntentDraftProjection,
): IntentWorkspaceProjection {
  return {
    schemaVersion: "1.0",
    projectId: previous?.projectId ?? projectId,
    current: accepted,
    history: [
      {
        revision: accepted.revision,
        revisionId: accepted.revisionId,
        revisionContentHash: accepted.revisionContentHash,
        createdAt: accepted.createdAt,
        primaryUseCase: accepted.primaryUseCase,
        status: accepted.status,
        unresolvedDecisionCount: accepted.unresolvedDecisions.length,
      },
      ...(previous?.history.filter((item) => item.revisionId !== accepted.revisionId) ?? []),
    ],
  };
}

export function persistedIntentUpdateMatchesCurrentProject(
  currentProject: IntentProjectIdentity | null,
  sourceProject: IntentProjectIdentity,
  workspace: Pick<IntentWorkspaceProjection, "projectId">,
): boolean {
  return intentProjectIdentityMatches(currentProject, sourceProject)
    && workspace.projectId === sourceProject.projectId;
}

export function intentProjectIdentityMatches(
  currentProject: IntentProjectIdentity | null,
  sourceProject: IntentProjectIdentity,
): boolean {
  return currentProject !== null
    && currentProject.projectId === sourceProject.projectId
    && currentProject.root === sourceProject.root;
}

interface IntentWorkspaceProps {
  readonly project: ProjectProjection | null;
  readonly announce: (message: string) => void;
  readonly transport?: CoreApiTransport;
  readonly initialWorkspace?: IntentWorkspaceProjection | undefined;
  readonly initialCatalog?: WorkflowProfileCatalogProjection | undefined;
  readonly onWorkspaceChange?: (
    workspace: IntentWorkspaceProjection,
    sourceProject: IntentProjectIdentity,
  ) => void;
}

interface IntentFormState {
  readonly primaryUseCase: PrimaryUseCase;
  readonly researchObjective: string;
  readonly contributionIntent: string;
  readonly phenomenon: string;
  readonly unitOfAnalysis: string;
  readonly levelOfAnalysis: string;
  readonly sourceKinds: IntentDraftRequest["sourceKinds"];
  readonly evidenceTypes: IntentDraftRequest["evidenceTypes"];
  readonly languageCodes: string;
  readonly startYear: string;
  readonly endYear: string;
  readonly includePrivateReports: boolean;
  readonly noveltyStandard: IntentDraftRequest["noveltyStandard"];
  readonly noveltyRationale: string;
  readonly autonomyLevel: IntentDraftRequest["autonomyLevel"];
  readonly stoppingConditions: IntentDraftRequest["stoppingConditions"];
  readonly revisionRationale: string;
}

const IMPACT_FIELD_KEYS: ReadonlySet<keyof IntentFormState> = new Set([
  "primaryUseCase",
  "sourceKinds",
  "languageCodes",
  "startYear",
  "endYear",
  "includePrivateReports",
  "evidenceTypes",
  "noveltyStandard",
  "autonomyLevel",
  "stoppingConditions",
]);

export function intentFieldAffectsImpact(key: keyof IntentFormState): boolean {
  return IMPACT_FIELD_KEYS.has(key);
}

function initialForm(
  current: IntentDraftProjection | null,
  catalog: WorkflowProfileCatalogProjection | null,
): IntentFormState {
  const guide = catalog ? selectedIntentGuidance(catalog, current?.primaryUseCase ?? "theory-synthesis") : null;
  return {
    primaryUseCase: current?.primaryUseCase ?? guide?.profileId ?? "theory-synthesis",
    researchObjective: current?.researchObjective ?? "",
    contributionIntent: current?.contributionIntent ?? "",
    phenomenon: current?.phenomenon ?? "",
    unitOfAnalysis: current?.unitOfAnalysis ?? "",
    levelOfAnalysis: current?.levelOfAnalysis ?? "",
    sourceKinds: current?.sourceKinds ?? [],
    evidenceTypes: current?.evidenceTypes ?? guide?.defaultEvidenceTypes ?? [],
    languageCodes: current?.languageCodes.join(", ") ?? "",
    startYear: current?.startYear?.toString() ?? "",
    endYear: current?.endYear?.toString() ?? "",
    includePrivateReports: current?.includePrivateReports ?? false,
    noveltyStandard: current ? current.noveltyStandard : guide?.defaultNoveltyStandard ?? null,
    noveltyRationale: current?.noveltyRationale ?? "",
    autonomyLevel: current?.autonomyLevel ?? guide?.defaultAutonomyLevel ?? "suggest",
    stoppingConditions: current?.stoppingConditions ?? guide?.defaultStoppingConditions ?? [],
    revisionRationale: "",
  };
}

function safeFailure(error: unknown): { readonly title: string; readonly message: string } {
  if (error instanceof CoreApiClientError) return { title: `${error.problem.title} (${error.problem.code})`, message: `${error.problem.detail} ${error.problem.remediation}` };
  return { title: "RO-CORE-INTENT-ACTION-FAILED", message: "The local intent action did not complete. The previous persisted revision remains authoritative." };
}

function idempotencyKey(): string {
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function IntentWorkspace({
  project,
  announce,
  transport = packagedProjectTransport,
  initialWorkspace,
  initialCatalog,
  onWorkspaceChange,
}: IntentWorkspaceProps): ReactNode {
  const client = useMemo(() => createCoreApiClient(transport), [transport]);
  const acceptanceCoordinator = useMemo(() => new IntentAcceptanceCoordinator(client), [client]);
  const availability = intentWorkspaceAvailability(project);
  const [workspace, setWorkspace] = useState<IntentWorkspaceProjection | null>(initialWorkspace ?? null);
  const [catalog, setCatalog] = useState<WorkflowProfileCatalogProjection | null>(initialCatalog ?? null);
  const [form, setForm] = useState<IntentFormState>(() => initialForm(initialWorkspace?.current ?? null, initialCatalog ?? null));
  const [impact, setImpact] = useState<IntentImpactPreview | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [acceptanceConfirmed, setAcceptanceConfirmed] = useState(false);
  const [acceptanceRationale, setAcceptanceRationale] = useState("");
  const [acceptanceAttempt, setAcceptanceAttempt] = useState<IntentAcceptanceAttempt | null>(null);
  const [formDirty, setFormDirty] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [busy, setBusy] = useState<"load" | "preview" | "save" | "accept" | null>(null);
  const [failure, setFailure] = useState<{ readonly title: string; readonly message: string } | null>(null);
  const onWorkspaceChangeRef = useRef(onWorkspaceChange);
  const activeProjectRef = useRef<IntentProjectIdentity | null>(null);
  activeProjectRef.current = project ? { projectId: project.projectId, root: project.root } : null;

  useEffect(() => {
    onWorkspaceChangeRef.current = onWorkspaceChange;
  }, [onWorkspaceChange]);

  useEffect(() => () => {
    activeProjectRef.current = null;
  }, []);

  useEffect(() => {
    if (initialCatalog) {
      setCatalog(initialCatalog);
      return;
    }
    let cancelled = false;
    void client.workflowProfileCatalog().then((next) => {
      if (!cancelled) setCatalog(next);
    }).catch((error: unknown) => {
      if (!cancelled) setFailure(safeFailure(error));
    });
    return () => { cancelled = true; };
  }, [client, initialCatalog]);

  useEffect(() => {
    if (catalog && !workspace?.current && !formDirty) setForm(initialForm(null, catalog));
  }, [catalog, formDirty, workspace?.current]);

  useEffect(() => {
    setImpact(null);
    setAcknowledged(false);
    setAcceptanceConfirmed(false);
    setAcceptanceRationale("");
    acceptanceCoordinator.reset();
    setAcceptanceAttempt(null);
    setFormDirty(false);
    setBusy(null);
    setFailure(null);
    if (initialWorkspace) {
      setWorkspace(initialWorkspace);
      setForm(initialForm(initialWorkspace.current, initialCatalog ?? null));
      return;
    }
    setWorkspace(null);
    if (!availability.available || !project) return;
    let cancelled = false;
    setBusy("load");
    void client.intent({ root: project.root }).then((next) => {
      if (!cancelled) {
        setWorkspace(next);
        setForm(initialForm(next.current, null));
        onWorkspaceChangeRef.current?.(next, { projectId: project.projectId, root: project.root });
      }
    }).catch((error: unknown) => {
      if (!cancelled) setFailure(safeFailure(error));
    }).finally(() => {
      if (!cancelled) setBusy(null);
    });
    return () => { cancelled = true; };
  }, [acceptanceCoordinator, availability.available, client, initialWorkspace, project]);

  const selectedProfile = catalog?.profiles.find((profile) => profile.profileId === form.primaryUseCase) ?? null;
  const guide = selectedProfile;
  const clearImpact = (): void => { setImpact(null); setAcknowledged(false); };
  const update = <K extends keyof IntentFormState>(key: K, value: IntentFormState[K]): void => {
    if (acceptanceAttempt) return;
    setForm((current) => ({ ...current, [key]: value }));
    setFormDirty(true);
    setAcceptanceConfirmed(false);
    if (intentFieldAffectsImpact(key)) clearImpact();
  };
  const languageCodes = (): string[] => form.languageCodes.split(",").map((value) => value.trim().toLowerCase()).filter(Boolean);
  const optionalYear = (value: string): number | null => value === "" ? null : Number(value);

  const preview = (): void => {
    if (!project || !workspace) return;
    const sourceProject = { projectId: project.projectId, root: project.root };
    setBusy("preview");
    setFailure(null);
    void client.previewIntent({
      root: project.root,
      expectedRevision: workspace.current?.revision ?? 0,
      primaryUseCase: form.primaryUseCase,
      sourceKinds: form.sourceKinds,
      languageCodes: languageCodes(),
      startYear: optionalYear(form.startYear),
      endYear: optionalYear(form.endYear),
      includePrivateReports: form.includePrivateReports,
      evidenceTypes: form.evidenceTypes,
      noveltyStandard: form.noveltyStandard,
      autonomyLevel: form.autonomyLevel,
      stoppingConditions: form.stoppingConditions,
    }).then((next) => {
      if (!intentProjectIdentityMatches(activeProjectRef.current, sourceProject)) return;
      setImpact(next);
      setAcknowledged(!next.acknowledgementRequired);
      announce(next.acknowledgementRequired ? "Revision impact preview ready. Review and acknowledge the affected workflow authority." : "Revision preview found no governed downstream scope change.");
    }).catch((error: unknown) => {
      if (intentProjectIdentityMatches(activeProjectRef.current, sourceProject)) setFailure(safeFailure(error));
    }).finally(() => {
      if (intentProjectIdentityMatches(activeProjectRef.current, sourceProject)) setBusy(null);
    });
  };

  const save = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (!project || !workspace || (impact?.acknowledgementRequired && !acknowledged)) return;
    const sourceProject = { projectId: project.projectId, root: project.root };
    setBusy("save");
    setFailure(null);
    void client.saveIntentDraft({
      root: project.root,
      expectedRevision: workspace.current?.revision ?? 0,
      impactAcknowledgement: acknowledged ? impact?.acknowledgementToken ?? null : null,
      primaryUseCase: form.primaryUseCase,
      researchObjective: form.researchObjective,
      contributionIntent: form.contributionIntent,
      phenomenon: form.phenomenon,
      unitOfAnalysis: form.unitOfAnalysis,
      levelOfAnalysis: form.levelOfAnalysis,
      sourceKinds: form.sourceKinds,
      evidenceTypes: form.evidenceTypes,
      languageCodes: languageCodes(),
      startYear: optionalYear(form.startYear),
      endYear: optionalYear(form.endYear),
      includePrivateReports: form.includePrivateReports,
      noveltyStandard: form.noveltyStandard,
      noveltyRationale: form.noveltyRationale,
      autonomyLevel: form.autonomyLevel,
      stoppingConditions: form.stoppingConditions,
      revisionRationale: form.revisionRationale,
    }, idempotencyKey()).then((current) => {
      const nextWorkspace: IntentWorkspaceProjection = {
        schemaVersion: "1.0",
        projectId: workspace.projectId,
        current,
        history: [
          { revision: current.revision, revisionId: current.revisionId, revisionContentHash: current.revisionContentHash, createdAt: current.createdAt, primaryUseCase: current.primaryUseCase, status: current.status, unresolvedDecisionCount: current.unresolvedDecisions.length },
          ...workspace.history,
        ],
      };
      if (!persistedIntentUpdateMatchesCurrentProject(activeProjectRef.current, sourceProject, nextWorkspace)) return;
      setWorkspace(nextWorkspace);
      onWorkspaceChangeRef.current?.(nextWorkspace, sourceProject);
      setForm((currentForm) => ({ ...currentForm, revisionRationale: "" }));
      setFormDirty(false);
      setAcceptanceConfirmed(false);
      setAcceptanceRationale("");
      acceptanceCoordinator.reset();
      setAcceptanceAttempt(null);
      clearImpact();
      announce(`Research intent draft revision ${current.revision} saved locally. It remains unable to launch analysis.`);
    }).catch((error: unknown) => {
      if (!intentProjectIdentityMatches(activeProjectRef.current, sourceProject)) return;
      const safe = safeFailure(error);
      setFailure(safe);
      announce(`Research intent draft was not saved. ${safe.title}`);
    }).finally(() => {
      if (intentProjectIdentityMatches(activeProjectRef.current, sourceProject)) setBusy(null);
    });
  };

  const accept = (): void => {
    const current = workspace?.current ?? null;
    const acceptance = intentAcceptanceAvailability(current);
    let attempt = acceptanceCoordinator.pendingAttempt();
    if (!attempt) {
      if (!project || !current || !acceptance.available || formDirty || !acceptanceConfirmed || !acceptanceRationale.trim()) return;
      attempt = acceptanceCoordinator.prepare(project.root, current, acceptanceRationale);
    }
    if (!project) return;
    const sourceProject = { projectId: project.projectId, root: project.root };
    setAcceptanceAttempt(attempt);
    setBusy("accept");
    setFailure(null);
    void acceptanceCoordinator.execute().then((result) => {
      if (result.status === "accepted") {
        const nextWorkspace = acceptedIntentWorkspace(workspace, sourceProject.projectId, result.accepted);
        if (!persistedIntentUpdateMatchesCurrentProject(activeProjectRef.current, sourceProject, nextWorkspace)) return;
        setWorkspace(nextWorkspace);
        onWorkspaceChangeRef.current?.(nextWorkspace, sourceProject);
        setForm(initialForm(result.accepted, catalog));
        setFormDirty(false);
        setAcceptanceConfirmed(false);
        setAcceptanceRationale("");
        setAcceptanceAttempt(null);
        announce(`Research intent revision ${result.accepted.revision} accepted. Downstream actions must cite and enforce its governing reference.`);
        return;
      }
      if (result.status === "rejected") {
        if (!intentProjectIdentityMatches(activeProjectRef.current, sourceProject)) return;
        const safe = safeFailure(result.error);
        setAcceptanceAttempt(null);
        setFailure(safe);
        announce(`Research intent was not accepted. ${safe.title}`);
        return;
      }
      if (!intentProjectIdentityMatches(activeProjectRef.current, sourceProject)) return;
      setAcceptanceAttempt(result.attempt);
      announce("Research intent acceptance outcome is unresolved. Retry the exact acceptance request to reconcile with Core before changing the draft.");
    }).finally(() => {
      if (intentProjectIdentityMatches(activeProjectRef.current, sourceProject)) setBusy(null);
    });
  };

  if (!availability.available) {
    return <section className="intent-workspace" aria-labelledby="intent-title"><div className="page-header"><Typography id="intent-title" as="h1" variant="page-title">Research Intent Contract</Typography></div><Notification tone="warning" title="Research intent unavailable">{availability.message}</Notification></section>;
  }

  return (
    <section className="intent-workspace" aria-labelledby="intent-title" data-intent-workspace="true">
      <div className="page-header">
        <Typography id="intent-title" as="h1" variant="page-title">Research Intent Contract</Typography>
        <Typography className="page-subtitle">Define a versioned, local research boundary before evidence work begins. Drafts never govern consequential analysis.</Typography>
      </div>
      {failure ? <Notification tone="danger" title={failure.title}>{failure.message}</Notification> : null}
      {!workspace ? <p role="status">{busy === "load" ? "Loading the local intent ledger…" : "Research intent could not be loaded."}</p> : (
        <form className="intent-form" onSubmit={save}>
          <Panel title="Purpose and intended contribution">
            <label htmlFor="intent-objective">Research objective</label>
            <textarea id="intent-objective" value={form.researchObjective} onChange={(event) => update("researchObjective", event.currentTarget.value)} rows={3} maxLength={4000} />
            <label htmlFor="intent-contribution">Intended contribution</label>
            <textarea id="intent-contribution" value={form.contributionIntent} onChange={(event) => update("contributionIntent", event.currentTarget.value)} rows={3} maxLength={4000} />
            <div className="intent-three-column">
              <label>Phenomenon<input value={form.phenomenon} onChange={(event) => update("phenomenon", event.currentTarget.value)} /></label>
              <label>Unit of analysis<input value={form.unitOfAnalysis} onChange={(event) => update("unitOfAnalysis", event.currentTarget.value)} /></label>
              <label>Level of analysis<input value={form.levelOfAnalysis} onChange={(event) => update("levelOfAnalysis", event.currentTarget.value)} /></label>
            </div>
          </Panel>

          <Panel title="Primary use case and guided workflow">
            <label htmlFor="intent-use-case">Primary use case</label>
            <select id="intent-use-case" value={form.primaryUseCase} onChange={(event) => {
              if (acceptanceAttempt) return;
              if (!catalog) return;
              const defaults = intentProfileSelectionDefaults(catalog, event.currentTarget.value as PrimaryUseCase);
              setForm((current) => ({ ...current, ...defaults }));
              setFormDirty(true);
              setAcceptanceConfirmed(false);
              clearImpact();
            }}>
              {catalog?.profiles.map((profile) => <option key={profile.profileId} value={profile.profileId}>{profile.title}</option>)}
            </select>
            <div className="intent-guidance">
              <p><strong>Purpose:</strong> {selectedProfile?.purpose ?? "Loading governed workflow profile…"}</p>
              <p><strong>Expected output:</strong> {selectedProfile?.expectedOutputs.join(", ") ?? "Unavailable"}</p>
              <p><strong>Process form:</strong> {selectedProfile ? selectedProfile.processForm === "revisitable" ? "Revisitable process" : "Linear process" : "Unavailable"}</p>
              {selectedProfile ? <ol>{selectedProfile.stages.map((stage) => <li key={stage.stageKey}>{stage.label}{stage.optional ? " (optional)" : ""}</li>)}</ol> : null}
              <p><strong>Example:</strong> {guide?.example ?? "Loading governed workflow guidance…"}</p>
              <Notification tone="warning" title="Workflow change has downstream effects">{guide?.warning ?? "Governed workflow guidance is unavailable."}</Notification>
              <p className="field-note">All tools remain available. Evidence and provenance requirements do not change with the selected profile.</p>
            </div>
          </Panel>

          <Panel title="Scope and evidence policy">
            <fieldset><legend>Source kinds</legend><label><input type="checkbox" checked={form.sourceKinds.includes("peer-reviewed-article")} onChange={(event) => update("sourceKinds", event.currentTarget.checked ? [...form.sourceKinds, "peer-reviewed-article"] : form.sourceKinds.filter((item) => item !== "peer-reviewed-article"))} /> Peer-reviewed articles</label><label><input type="checkbox" checked={form.sourceKinds.includes("technical-report")} onChange={(event) => update("sourceKinds", event.currentTarget.checked ? [...form.sourceKinds, "technical-report"] : form.sourceKinds.filter((item) => item !== "technical-report"))} /> Technical reports</label><label><input type="checkbox" checked={form.includePrivateReports} onChange={(event) => update("includePrivateReports", event.currentTarget.checked)} /> Include authorized private reports</label></fieldset>
            <div className="intent-three-column"><label>Languages (comma-separated)<input value={form.languageCodes} onChange={(event) => update("languageCodes", event.currentTarget.value)} /></label><label>Start year<input type="number" min="1000" max="9999" value={form.startYear} onChange={(event) => update("startYear", event.currentTarget.value)} /></label><label>End year<input type="number" min="1000" max="9999" value={form.endYear} onChange={(event) => update("endYear", event.currentTarget.value)} /></label></div>
            <fieldset><legend>Evidence types</legend>{EVIDENCE_TYPES.map((evidenceType) => <label key={evidenceType}><input type="checkbox" checked={form.evidenceTypes.includes(evidenceType)} onChange={(event) => update("evidenceTypes", event.currentTarget.checked ? [...form.evidenceTypes, evidenceType] : form.evidenceTypes.filter((item) => item !== evidenceType))} /> {evidenceType}</label>)}</fieldset>
            <p className="field-note">Mode recommendation: {guide?.defaultEvidenceTypes.join(", ") ?? "Loading…"}. Corpus-scope changes require a fresh impact preview.</p>
          </Panel>

          <div className="intent-two-column">
            <Panel title="AI authority profile"><label htmlFor="intent-autonomy">Maximum autonomy</label><select id="intent-autonomy" value={form.autonomyLevel} onChange={(event) => update("autonomyLevel", event.currentTarget.value as IntentDraftRequest["autonomyLevel"])}><option value="human-only">Human only</option><option value="suggest">Suggest only</option><option value="prepare-reversible">Prepare reversible work</option><option value="execute-reversible">Execute reversible work</option></select><p className="field-note">Ethics, study conduct, authorship, interpretation, final claims, and publication remain human decisions.</p></Panel>
            <Panel title="Novelty standard"><label htmlFor="intent-novelty">Standard</label><select id="intent-novelty" value={form.noveltyStandard ?? ""} onChange={(event) => update("noveltyStandard", event.currentTarget.value ? event.currentTarget.value as NoveltyStandard : null)}><option value="">Not yet decided</option>{["bounded-comparative", "incremental", "theoretical", "methodological", "contextual", "critical", "interpretive", "not-claimed"].map((value) => <option key={value} value={value}>{value}</option>)}</select><label htmlFor="intent-novelty-rationale">Rationale</label><textarea id="intent-novelty-rationale" value={form.noveltyRationale} onChange={(event) => update("noveltyRationale", event.currentTarget.value)} rows={3} /></Panel>
          </div>

          <Panel title="Stopping logic"><fieldset><legend>Bounded stopping conditions</legend>{(["source-exhaustion", "coverage-threshold", "interpretive-saturation", "benchmark-complete", "nearest-prior-work-challenged", "protocol-complete", "resource-budget", "researcher-decision"] as const).map((condition) => <label key={condition}><input type="checkbox" checked={form.stoppingConditions.includes(condition)} onChange={(event) => update("stoppingConditions", event.currentTarget.checked ? [...form.stoppingConditions, condition] : form.stoppingConditions.filter((item) => item !== condition))} /> {condition}</label>)}</fieldset></Panel>

          <Panel title="Preview revision effects" tone={impact?.acknowledgementRequired ? "warning" : "neutral"}>
            <p>Review changes to the primary workflow, corpus boundary, or novelty scope before saving a new immutable revision.</p>
            <Button type="button" disabled={busy !== null || acceptanceAttempt !== null} onClick={preview}>{busy === "preview" ? "Preparing preview…" : "Preview revision effects"}</Button>
            {impact ? <div className="intent-impact" aria-live="polite"><p><strong>Affected workflows:</strong> {impact.affectedWorkflows.join(", ") || "None"}</p><p><strong>Affected schemas:</strong> {impact.affectedSchemas.join(", ") || "None"}</p><p><strong>Affected checkpoints:</strong> {impact.affectedCheckpoints.join(", ") || "None"}</p><p><strong>Affected outputs:</strong> {impact.affectedOutputs.join(", ") || "None"}</p><p><strong>Autonomy defaults:</strong> {impact.autonomyDefaultEffects.join(", ") || "No effect"}</p><p><strong>Stopping logic:</strong> {impact.stoppingLogicEffects.join(", ") || "No effect"}</p><p><strong>Stale artifacts:</strong> {impact.staleArtifactIds.join(", ") || "None currently identified"}</p><p>All tools remain {impact.allToolsAccessible ? "available" : "restricted"}; evidence requirements {impact.evidenceRequirementsUnchanged ? "remain unchanged" : "changed"}; provenance requirements {impact.provenanceRequirementsUnchanged ? "remain unchanged" : "changed"}.</p>{impact.warnings.map((warning) => <p key={warning}>{warning}</p>)}{impact.acknowledgementRequired ? <label className="consent-boundary"><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.currentTarget.checked)} /><span>I reviewed the exact schemas, checkpoints, outputs, autonomy, stopping, and staleness effects and authorize this draft revision.</span></label> : null}</div> : null}
          </Panel>

          <Panel title="Save or accept intent revision">
            <label htmlFor="intent-rationale">Revision rationale</label><textarea id="intent-rationale" value={form.revisionRationale} onChange={(event) => update("revisionRationale", event.currentTarget.value)} rows={2} required />
            {workspace.current ? <p><StatusBadge tone={workspace.current.status === "accepted" || workspace.current.decisionComplete ? "success" : "warning"}>Revision {workspace.current.revision} · {workspace.current.status === "accepted" ? "accepted" : workspace.current.decisionComplete ? "decision complete draft" : `${workspace.current.unresolvedDecisions.length} unresolved`}</StatusBadge></p> : <p>No intent revision has been saved.</p>}
            <div className="intent-actions"><Button tone="primary" type="submit" disabled={busy !== null || acceptanceAttempt !== null || (impact?.acknowledgementRequired === true && !acknowledged)}>{busy === "save" ? "Saving locally…" : "Save draft revision"}</Button><Button type="button" aria-expanded={showHistory} onClick={() => setShowHistory((value) => !value)}>Compare versions</Button><Button type="button" disabled>Launch gated analysis</Button></div>
            <div className="intent-acceptance">
              {acceptanceAttempt ? <Notification tone="warning" title={busy === "accept" ? "Acceptance request in progress" : "Acceptance outcome unresolved"}>Revision {acceptanceAttempt.command.expectedRevision} and content hash <code>{acceptanceAttempt.command.expectedRevisionContentHash.slice(0, 20)}…</code> remain frozen. Retry sends the same confirmed command and idempotency key; do not change the draft until Core returns the authoritative accepted revision.</Notification> : null}
              <label htmlFor="intent-acceptance-rationale">Human acceptance rationale</label>
              <textarea id="intent-acceptance-rationale" value={acceptanceRationale} onChange={(event) => { setAcceptanceRationale(event.currentTarget.value); setAcceptanceConfirmed(false); }} rows={2} disabled={acceptanceAttempt !== null || !intentAcceptanceAvailability(workspace.current).available || formDirty} />
              <label className="consent-boundary"><input type="checkbox" checked={acceptanceConfirmed} onChange={(event) => setAcceptanceConfirmed(event.currentTarget.checked)} disabled={acceptanceAttempt !== null || !intentAcceptanceAvailability(workspace.current).available || formDirty || !acceptanceRationale.trim()} /><span>I reviewed and confirm persisted revision {workspace.current?.revision ?? 0} and content hash <code>{workspace.current?.revisionContentHash.slice(0, 20) ?? "unavailable"}…</code>.</span></label>
              <Button type="button" disabled={busy !== null || (acceptanceAttempt === null && (formDirty || !intentAcceptanceAvailability(workspace.current).available || !acceptanceConfirmed || !acceptanceRationale.trim()))} onClick={accept}>{busy === "accept" ? "Reconciling exact acceptance…" : acceptanceAttempt ? "Retry exact acceptance" : "Accept intent revision"}</Button>
              <p className="field-note">{acceptanceAttempt ? "The exact acceptance request remains frozen until Core confirms acceptance or returns a definitive rejection." : formDirty ? "Save or discard the unsaved edits before accepting the persisted revision." : intentAcceptanceAvailability(workspace.current).message}</p>
            </div>
            <p className="field-note">Launch remains disabled for drafts. Later workflow actions must evaluate the accepted governing intent at the service boundary.</p>
            {showHistory ? <ol className="intent-history">{workspace.history.map((item) => <li key={item.revisionId}>Revision {item.revision} · {item.primaryUseCase} · {item.unresolvedDecisionCount} unresolved · <code>{item.revisionContentHash.slice(0, 20)}…</code></li>)}</ol> : null}
          </Panel>
        </form>
      )}
    </section>
  );
}
