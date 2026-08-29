import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";

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
} from "@research-observatory/contracts/core-api";
import { Button, Notification, Panel, StatusBadge, Typography } from "@research-observatory/ui-components";

import { packagedProjectTransport } from "./ProjectsWorkspace";

type PrimaryUseCase = IntentDraftRequest["primaryUseCase"];
type EvidenceType = IntentDraftRequest["evidenceTypes"][number];
type NoveltyStandard = NonNullable<IntentDraftRequest["noveltyStandard"]>;
type StoppingCondition = IntentDraftRequest["stoppingConditions"][number];

const EVIDENCE_TYPES: readonly EvidenceType[] = [
  "empirical-study", "systematic-review", "theoretical-work", "technical-evaluation", "standard",
  "dataset", "interpretive-text", "stakeholder-account", "critical-analysis", "private-report",
];

export interface IntentModeGuidance {
  readonly id: PrimaryUseCase;
  readonly label: string;
  readonly group: "Evidence synthesis" | "Inquiry" | "Study and article development";
  readonly epistemicMode: IntentDraftProjection["epistemicMode"];
  readonly workflow: string;
  readonly example: string;
  readonly defaultEvidenceTypes: readonly EvidenceType[];
  readonly defaultNoveltyStandard: NoveltyStandard;
  readonly defaultStoppingConditions: readonly StoppingCondition[];
  readonly warning: string;
}

export const INTENT_MODE_GUIDANCE: readonly IntentModeGuidance[] = Object.freeze([
  { id: "rapid-orientation", label: "Rapid orientation", group: "Evidence synthesis", epistemicMode: "systematic", workflow: "Question Framing → Search Brief → Evidence Map", example: "Map the main approaches and unresolved questions in a new field.", defaultEvidenceTypes: ["empirical-study", "systematic-review"], defaultNoveltyStandard: "not-claimed", defaultStoppingConditions: ["coverage-threshold"], warning: "Rapid orientation supports bounded understanding; it does not claim exhaustive coverage." },
  { id: "systematic-review", label: "Systematic review", group: "Evidence synthesis", epistemicMode: "systematic", workflow: "Protocol → Search → Screening → Extraction → Synthesis", example: "Estimate and explain an intervention effect from eligible studies.", defaultEvidenceTypes: ["empirical-study", "systematic-review"], defaultNoveltyStandard: "bounded-comparative", defaultStoppingConditions: ["coverage-threshold"], warning: "Coverage claims remain bounded by the recorded protocol, sources, dates, and languages." },
  { id: "living-review", label: "Living review", group: "Evidence synthesis", epistemicMode: "systematic", workflow: "Protocol → Monitored Search → Screening → Versioned Synthesis", example: "Maintain an evidence synthesis as qualifying studies appear.", defaultEvidenceTypes: ["empirical-study", "systematic-review"], defaultNoveltyStandard: "incremental", defaultStoppingConditions: ["coverage-threshold", "researcher-decision"], warning: "Every update preserves its search boundary and prior synthesis revision." },
  { id: "theory-synthesis", label: "Theory synthesis", group: "Inquiry", epistemicMode: "theory", workflow: "Concept Inventory → Proposition Ledger → Theory Map → Synthesis", example: "Reconcile competing mechanisms into a bounded conceptual model.", defaultEvidenceTypes: ["theoretical-work", "empirical-study"], defaultNoveltyStandard: "theoretical", defaultStoppingConditions: ["interpretive-saturation"], warning: "Conceptual integration must preserve disagreements and evidentiary limits." },
  { id: "hermeneutic-inquiry", label: "Hermeneutic inquiry", group: "Inquiry", epistemicMode: "hermeneutic", workflow: "Interpretive Frame → Reading Cycle → Meaning Ledger → Account", example: "Develop a situated interpretation across a bounded textual corpus.", defaultEvidenceTypes: ["interpretive-text"], defaultNoveltyStandard: "interpretive", defaultStoppingConditions: ["interpretive-saturation", "researcher-decision"], warning: "Interpretations remain researcher-authored and tied to the recorded corpus and frame." },
  { id: "critical-problematization", label: "Critical problematization", group: "Inquiry", epistemicMode: "critical", workflow: "Assumption Inventory → Tension Analysis → Counter-position → Critique", example: "Surface exclusions and consequences within a dominant framing.", defaultEvidenceTypes: ["critical-analysis", "stakeholder-account"], defaultNoveltyStandard: "critical", defaultStoppingConditions: ["interpretive-saturation", "researcher-decision"], warning: "The workflow must preserve standpoint, counter-evidence, and affected voices." },
  { id: "technical-landscape", label: "Technical landscape", group: "Evidence synthesis", epistemicMode: "technical", workflow: "Capability Frame → Artifact Inventory → Benchmark Map → Landscape", example: "Compare architectures and evaluated capabilities for a technical domain.", defaultEvidenceTypes: ["technical-evaluation", "standard", "dataset"], defaultNoveltyStandard: "bounded-comparative", defaultStoppingConditions: ["benchmark-complete"], warning: "Comparisons are limited to compatible evidence, versions, and benchmark conditions." },
  { id: "novelty-audit", label: "Novelty audit", group: "Evidence synthesis", epistemicMode: "novelty", workflow: "Claim Decomposition → Nearest Prior Work → Difference Ledger → Audit", example: "Challenge a proposed contribution against the closest documented alternatives.", defaultEvidenceTypes: ["empirical-study", "theoretical-work", "technical-evaluation"], defaultNoveltyStandard: "bounded-comparative", defaultStoppingConditions: ["nearest-prior-work-challenged"], warning: "A novelty claim is provisional until nearest prior work and plausible counterexamples are challenged." },
  { id: "empirical-study-design", label: "Empirical study design", group: "Study and article development", epistemicMode: "empirical", workflow: "Question → Construct Map → Design Alternatives → Protocol", example: "Design a study without inventing participants, results, or feasibility evidence.", defaultEvidenceTypes: ["empirical-study", "systematic-review"], defaultNoveltyStandard: "methodological", defaultStoppingConditions: ["protocol-complete"], warning: "The researcher retains authority over ethics, recruitment, conduct, and interpretation." },
  { id: "empirical-study-to-article", label: "Empirical study to article", group: "Study and article development", epistemicMode: "empirical", workflow: "Study Record → Analysis Plan → Claim Ledger → Article", example: "Develop a manuscript from a documented study and analysis plan.", defaultEvidenceTypes: ["empirical-study", "dataset"], defaultNoveltyStandard: "contextual", defaultStoppingConditions: ["protocol-complete", "researcher-decision"], warning: "Unreported or missing results remain unreported or missing." },
  { id: "empirical-results-to-article", label: "Empirical results to article", group: "Study and article development", epistemicMode: "empirical", workflow: "Result Import → Robustness Review → Claim Ledger → Article", example: "Develop an article from completed, traceable empirical results.", defaultEvidenceTypes: ["empirical-study", "dataset"], defaultNoveltyStandard: "incremental", defaultStoppingConditions: ["researcher-decision"], warning: "No result, statistic, or participant detail may be inferred when absent." },
  { id: "theory-article-development", label: "Theory article development", group: "Study and article development", epistemicMode: "theory", workflow: "Contribution Frame → Theory Map → Argument Ledger → Article", example: "Develop a theory article from traceable concepts and propositions.", defaultEvidenceTypes: ["theoretical-work", "empirical-study"], defaultNoveltyStandard: "theoretical", defaultStoppingConditions: ["interpretive-saturation", "researcher-decision"], warning: "The system can prepare arguments; the researcher owns interpretation and claims." },
  { id: "critical-article-development", label: "Critical article development", group: "Study and article development", epistemicMode: "critical", workflow: "Problem Frame → Assumption Ledger → Counter-position → Article", example: "Develop a critical article with explicit standpoint and counter-evidence.", defaultEvidenceTypes: ["critical-analysis", "stakeholder-account", "interpretive-text"], defaultNoveltyStandard: "critical", defaultStoppingConditions: ["interpretive-saturation", "researcher-decision"], warning: "The article must not erase contested positions or affected perspectives." },
  { id: "manuscript-review-revision", label: "Manuscript review and revision", group: "Study and article development", epistemicMode: "technical", workflow: "Review Intake → Response Ledger → Revision Plan → Verified Draft", example: "Address reviewer comments without silently broadening claims.", defaultEvidenceTypes: ["empirical-study", "theoretical-work", "technical-evaluation"], defaultNoveltyStandard: "not-claimed", defaultStoppingConditions: ["researcher-decision"], warning: "Reviewer responses and claim changes remain explicit, traceable researcher decisions." },
]);

export function selectedIntentGuidance(useCase: PrimaryUseCase): IntentModeGuidance {
  const guidance = INTENT_MODE_GUIDANCE.find((candidate) => candidate.id === useCase);
  if (!guidance) throw new Error("RO-CORE-INTENT-MODE-INVALID");
  return guidance;
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

interface IntentWorkspaceProps {
  readonly project: ProjectProjection | null;
  readonly announce: (message: string) => void;
  readonly transport?: CoreApiTransport;
  readonly initialWorkspace?: IntentWorkspaceProjection;
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

function initialForm(current: IntentDraftProjection | null): IntentFormState {
  const guide = selectedIntentGuidance(current?.primaryUseCase ?? "theory-synthesis");
  return {
    primaryUseCase: guide.id,
    researchObjective: current?.researchObjective ?? "",
    contributionIntent: current?.contributionIntent ?? "",
    phenomenon: current?.phenomenon ?? "",
    unitOfAnalysis: current?.unitOfAnalysis ?? "",
    levelOfAnalysis: current?.levelOfAnalysis ?? "",
    sourceKinds: current?.sourceKinds ?? [],
    evidenceTypes: current?.evidenceTypes ?? guide.defaultEvidenceTypes,
    languageCodes: current?.languageCodes.join(", ") ?? "",
    startYear: current?.startYear?.toString() ?? "",
    endYear: current?.endYear?.toString() ?? "",
    includePrivateReports: current?.includePrivateReports ?? false,
    noveltyStandard: current?.noveltyStandard ?? null,
    noveltyRationale: current?.noveltyRationale ?? "",
    autonomyLevel: current?.autonomyLevel ?? "suggest",
    stoppingConditions: current?.stoppingConditions ?? guide.defaultStoppingConditions,
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

export function IntentWorkspace({ project, announce, transport = packagedProjectTransport, initialWorkspace }: IntentWorkspaceProps): ReactNode {
  const client = useMemo(() => createCoreApiClient(transport), [transport]);
  const availability = intentWorkspaceAvailability(project);
  const [workspace, setWorkspace] = useState<IntentWorkspaceProjection | null>(initialWorkspace ?? null);
  const [form, setForm] = useState<IntentFormState>(() => initialForm(initialWorkspace?.current ?? null));
  const [impact, setImpact] = useState<IntentImpactPreview | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [acceptanceConfirmed, setAcceptanceConfirmed] = useState(false);
  const [acceptanceRationale, setAcceptanceRationale] = useState("");
  const [formDirty, setFormDirty] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [busy, setBusy] = useState<"load" | "preview" | "save" | "accept" | null>(null);
  const [failure, setFailure] = useState<{ readonly title: string; readonly message: string } | null>(null);

  useEffect(() => {
    setImpact(null);
    setAcknowledged(false);
    setAcceptanceConfirmed(false);
    setAcceptanceRationale("");
    setFormDirty(false);
    setFailure(null);
    if (initialWorkspace) {
      setWorkspace(initialWorkspace);
      setForm(initialForm(initialWorkspace.current));
      return;
    }
    setWorkspace(null);
    if (!availability.available || !project) return;
    let cancelled = false;
    setBusy("load");
    void client.intent({ root: project.root }).then((next) => {
      if (!cancelled) {
        setWorkspace(next);
        setForm(initialForm(next.current));
      }
    }).catch((error: unknown) => {
      if (!cancelled) setFailure(safeFailure(error));
    }).finally(() => {
      if (!cancelled) setBusy(null);
    });
    return () => { cancelled = true; };
  }, [availability.available, client, initialWorkspace, project]);

  const guide = selectedIntentGuidance(form.primaryUseCase);
  const clearImpact = (): void => { setImpact(null); setAcknowledged(false); };
  const update = <K extends keyof IntentFormState>(key: K, value: IntentFormState[K], affectsImpact = false): void => {
    setForm((current) => ({ ...current, [key]: value }));
    setFormDirty(true);
    setAcceptanceConfirmed(false);
    if (affectsImpact) clearImpact();
  };
  const languageCodes = (): string[] => form.languageCodes.split(",").map((value) => value.trim().toLowerCase()).filter(Boolean);
  const optionalYear = (value: string): number | null => value === "" ? null : Number(value);

  const preview = (): void => {
    if (!project || !workspace) return;
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
      noveltyStandard: form.noveltyStandard,
    }).then((next) => {
      setImpact(next);
      setAcknowledged(!next.acknowledgementRequired);
      announce(next.acknowledgementRequired ? "Revision impact preview ready. Review and acknowledge every affected workflow and output." : "Revision preview found no governed downstream scope change.");
    }).catch((error: unknown) => setFailure(safeFailure(error))).finally(() => setBusy(null));
  };

  const save = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (!project || !workspace || (impact?.acknowledgementRequired && !acknowledged)) return;
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
      setWorkspace((previous) => ({
        schemaVersion: "1.0",
        projectId: previous?.projectId ?? project.projectId,
        current,
        history: [
          { revision: current.revision, revisionId: current.revisionId, revisionContentHash: current.revisionContentHash, createdAt: current.createdAt, primaryUseCase: current.primaryUseCase, status: current.status, unresolvedDecisionCount: current.unresolvedDecisions.length },
          ...(previous?.history ?? []),
        ],
      }));
      setForm((currentForm) => ({ ...currentForm, revisionRationale: "" }));
      setFormDirty(false);
      setAcceptanceConfirmed(false);
      setAcceptanceRationale("");
      clearImpact();
      announce(`Research intent draft revision ${current.revision} saved locally. It remains unable to launch analysis.`);
    }).catch((error: unknown) => {
      const safe = safeFailure(error);
      setFailure(safe);
      announce(`Research intent draft was not saved. ${safe.title}`);
    }).finally(() => setBusy(null));
  };

  const accept = (): void => {
    const current = workspace?.current ?? null;
    const acceptance = intentAcceptanceAvailability(current);
    if (!project || !current || !acceptance.available || formDirty || !acceptanceConfirmed || !acceptanceRationale.trim()) return;
    setBusy("accept");
    setFailure(null);
    void client.acceptIntent(
      intentAcceptanceRequest(project.root, current, acceptanceRationale),
      idempotencyKey(),
    ).then((accepted) => {
      setWorkspace((previous) => ({
        schemaVersion: "1.0",
        projectId: previous?.projectId ?? project.projectId,
        current: accepted,
        history: [
          { revision: accepted.revision, revisionId: accepted.revisionId, revisionContentHash: accepted.revisionContentHash, createdAt: accepted.createdAt, primaryUseCase: accepted.primaryUseCase, status: accepted.status, unresolvedDecisionCount: accepted.unresolvedDecisions.length },
          ...(previous?.history.filter((item) => item.revisionId !== accepted.revisionId) ?? []),
        ],
      }));
      setForm(initialForm(accepted));
      setFormDirty(false);
      setAcceptanceConfirmed(false);
      setAcceptanceRationale("");
      announce(`Research intent revision ${accepted.revision} accepted. Downstream actions must cite and enforce its governing reference.`);
    }).catch((error: unknown) => {
      const safe = safeFailure(error);
      setFailure(safe);
      announce(`Research intent was not accepted. ${safe.title}`);
    }).finally(() => setBusy(null));
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
              const next = selectedIntentGuidance(event.currentTarget.value as PrimaryUseCase);
              setForm((current) => ({ ...current, primaryUseCase: next.id, evidenceTypes: next.defaultEvidenceTypes, noveltyStandard: next.defaultNoveltyStandard, stoppingConditions: next.defaultStoppingConditions }));
              setFormDirty(true);
              setAcceptanceConfirmed(false);
              clearImpact();
            }}>
              {(["Evidence synthesis", "Inquiry", "Study and article development"] as const).map((group) => <optgroup key={group} label={group}>{INTENT_MODE_GUIDANCE.filter((item) => item.group === group).map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</optgroup>)}
            </select>
            <div className="intent-guidance"><p><strong>Workflow:</strong> {guide.workflow}</p><p><strong>Example:</strong> {guide.example}</p><Notification tone="warning" title="Workflow change has downstream effects">{guide.warning}</Notification></div>
          </Panel>

          <Panel title="Scope and evidence policy">
            <fieldset><legend>Source kinds</legend><label><input type="checkbox" checked={form.sourceKinds.includes("peer-reviewed-article")} onChange={(event) => update("sourceKinds", event.currentTarget.checked ? [...form.sourceKinds, "peer-reviewed-article"] : form.sourceKinds.filter((item) => item !== "peer-reviewed-article"), true)} /> Peer-reviewed articles</label><label><input type="checkbox" checked={form.sourceKinds.includes("technical-report")} onChange={(event) => update("sourceKinds", event.currentTarget.checked ? [...form.sourceKinds, "technical-report"] : form.sourceKinds.filter((item) => item !== "technical-report"), true)} /> Technical reports</label><label><input type="checkbox" checked={form.includePrivateReports} onChange={(event) => update("includePrivateReports", event.currentTarget.checked, true)} /> Include authorized private reports</label></fieldset>
            <div className="intent-three-column"><label>Languages (comma-separated)<input value={form.languageCodes} onChange={(event) => update("languageCodes", event.currentTarget.value, true)} /></label><label>Start year<input type="number" min="1000" max="9999" value={form.startYear} onChange={(event) => update("startYear", event.currentTarget.value, true)} /></label><label>End year<input type="number" min="1000" max="9999" value={form.endYear} onChange={(event) => update("endYear", event.currentTarget.value, true)} /></label></div>
            <fieldset><legend>Evidence types</legend>{EVIDENCE_TYPES.map((evidenceType) => <label key={evidenceType}><input type="checkbox" checked={form.evidenceTypes.includes(evidenceType)} onChange={(event) => update("evidenceTypes", event.currentTarget.checked ? [...form.evidenceTypes, evidenceType] : form.evidenceTypes.filter((item) => item !== evidenceType))} /> {evidenceType}</label>)}</fieldset>
            <p className="field-note">Mode recommendation: {guide.defaultEvidenceTypes.join(", ")}. Corpus-scope changes require a fresh impact preview.</p>
          </Panel>

          <div className="intent-two-column">
            <Panel title="AI authority profile"><label htmlFor="intent-autonomy">Maximum autonomy</label><select id="intent-autonomy" value={form.autonomyLevel} onChange={(event) => update("autonomyLevel", event.currentTarget.value as IntentDraftRequest["autonomyLevel"])}><option value="human-only">Human only</option><option value="suggest">Suggest only</option><option value="prepare-reversible">Prepare reversible work</option><option value="execute-reversible">Execute reversible work</option></select><p className="field-note">Ethics, study conduct, authorship, interpretation, final claims, and publication remain human decisions.</p></Panel>
            <Panel title="Novelty standard"><label htmlFor="intent-novelty">Standard</label><select id="intent-novelty" value={form.noveltyStandard ?? ""} onChange={(event) => update("noveltyStandard", event.currentTarget.value ? event.currentTarget.value as NoveltyStandard : null, true)}><option value="">Not yet decided</option>{["bounded-comparative", "incremental", "theoretical", "methodological", "contextual", "critical", "interpretive", "not-claimed"].map((value) => <option key={value} value={value}>{value}</option>)}</select><label htmlFor="intent-novelty-rationale">Rationale</label><textarea id="intent-novelty-rationale" value={form.noveltyRationale} onChange={(event) => update("noveltyRationale", event.currentTarget.value)} rows={3} /></Panel>
          </div>

          <Panel title="Stopping logic"><fieldset><legend>Bounded stopping conditions</legend>{(["source-exhaustion", "coverage-threshold", "interpretive-saturation", "benchmark-complete", "nearest-prior-work-challenged", "protocol-complete", "resource-budget", "researcher-decision"] as const).map((condition) => <label key={condition}><input type="checkbox" checked={form.stoppingConditions.includes(condition)} onChange={(event) => update("stoppingConditions", event.currentTarget.checked ? [...form.stoppingConditions, condition] : form.stoppingConditions.filter((item) => item !== condition))} /> {condition}</label>)}</fieldset></Panel>

          <Panel title="Preview revision effects" tone={impact?.acknowledgementRequired ? "warning" : "neutral"}>
            <p>Review changes to the primary workflow, corpus boundary, or novelty scope before saving a new immutable revision.</p>
            <Button type="button" disabled={busy !== null} onClick={preview}>{busy === "preview" ? "Preparing preview…" : "Preview revision effects"}</Button>
            {impact ? <div className="intent-impact" aria-live="polite"><p><strong>Affected workflows:</strong> {impact.affectedWorkflows.join(", ") || "None"}</p><p><strong>Affected outputs:</strong> {impact.affectedOutputs.join(", ") || "None"}</p>{impact.warnings.map((warning) => <p key={warning}>{warning}</p>)}{impact.acknowledgementRequired ? <label className="consent-boundary"><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.currentTarget.checked)} /><span>I reviewed the exact affected workflows and outputs and authorize this draft revision.</span></label> : null}</div> : null}
          </Panel>

          <Panel title="Save or accept intent revision">
            <label htmlFor="intent-rationale">Revision rationale</label><textarea id="intent-rationale" value={form.revisionRationale} onChange={(event) => update("revisionRationale", event.currentTarget.value)} rows={2} required />
            {workspace.current ? <p><StatusBadge tone={workspace.current.status === "accepted" || workspace.current.decisionComplete ? "success" : "warning"}>Revision {workspace.current.revision} · {workspace.current.status === "accepted" ? "accepted" : workspace.current.decisionComplete ? "decision complete draft" : `${workspace.current.unresolvedDecisions.length} unresolved`}</StatusBadge></p> : <p>No intent revision has been saved.</p>}
            <div className="intent-actions"><Button tone="primary" type="submit" disabled={busy !== null || (impact?.acknowledgementRequired === true && !acknowledged)}>{busy === "save" ? "Saving locally…" : "Save draft revision"}</Button><Button type="button" aria-expanded={showHistory} onClick={() => setShowHistory((value) => !value)}>Compare versions</Button><Button type="button" disabled>Launch gated analysis</Button></div>
            <div className="intent-acceptance">
              <label htmlFor="intent-acceptance-rationale">Human acceptance rationale</label>
              <textarea id="intent-acceptance-rationale" value={acceptanceRationale} onChange={(event) => { setAcceptanceRationale(event.currentTarget.value); setAcceptanceConfirmed(false); }} rows={2} disabled={!intentAcceptanceAvailability(workspace.current).available || formDirty} />
              <label className="consent-boundary"><input type="checkbox" checked={acceptanceConfirmed} onChange={(event) => setAcceptanceConfirmed(event.currentTarget.checked)} disabled={!intentAcceptanceAvailability(workspace.current).available || formDirty || !acceptanceRationale.trim()} /><span>I reviewed and confirm persisted revision {workspace.current?.revision ?? 0} and content hash <code>{workspace.current?.revisionContentHash.slice(0, 20) ?? "unavailable"}…</code>.</span></label>
              <Button type="button" disabled={busy !== null || formDirty || !intentAcceptanceAvailability(workspace.current).available || !acceptanceConfirmed || !acceptanceRationale.trim()} onClick={accept}>{busy === "accept" ? "Accepting exact revision…" : "Accept intent revision"}</Button>
              <p className="field-note">{formDirty ? "Save or discard the unsaved edits before accepting the persisted revision." : intentAcceptanceAvailability(workspace.current).message}</p>
            </div>
            <p className="field-note">Launch remains disabled for drafts. Later workflow actions must evaluate the accepted governing intent at the service boundary.</p>
            {showHistory ? <ol className="intent-history">{workspace.history.map((item) => <li key={item.revisionId}>Revision {item.revision} · {item.primaryUseCase} · {item.unresolvedDecisionCount} unresolved · <code>{item.revisionContentHash.slice(0, 20)}…</code></li>)}</ol> : null}
          </Panel>
        </form>
      )}
    </section>
  );
}
