import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";

import {
  CoreApiClientError,
  createCoreApiClient,
  type CoreApiTransport,
  type IntentDraftProjection,
  type IntentWorkspaceProjection,
  type ProjectProjection,
  type ProvenanceLineageNode,
  type ProvenanceLineagePage,
  type ProvenanceLineageRequest,
  type RecalculationCauseProjection,
  type RecalculationComparisonProjection,
  type RecalculationPreview,
  type RecalculationRestoreReviewProjection,
  type RecalculationRestoredRevision,
  type RecalculationScheduleProjection,
} from "@research-observatory/contracts/core-api";
import { Button, Panel, StatusBadge, Typography } from "@research-observatory/ui-components";

import { packagedProjectTransport } from "./ProjectsWorkspace";

const UUID_V7 = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const PAGE_SIZE = 50;
const MAX_DEPTH = 8;

type CoreApiClient = ReturnType<typeof createCoreApiClient>;
export type RecalculationImpactClass = "automatic" | "review-required" | "blocked";

export function recalculationImpactClass(cause: RecalculationCauseProjection): RecalculationImpactClass {
  if (cause.disposition === "unknown-impact") return "blocked";
  return cause.reviewRequired ? "review-required" : "automatic";
}

export function acceptedRecalculationIntent(workspace: IntentWorkspaceProjection): IntentDraftProjection | null {
  return workspace.current?.status === "accepted" ? workspace.current : null;
}

function commandId(): string {
  if (!globalThis.crypto) throw new Error("RO-CORE-CRYPTO-UNAVAILABLE");
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
}

function assertInspectableProject(project: ProjectProjection, revisionId?: string): void {
  if (!project.open || project.accessMode === "closed" || project.compatibilityState !== "compatible"
    || (revisionId !== undefined && !UUID_V7.test(revisionId))) {
    throw new Error("RO-CORE-REQUEST-INVALID");
  }
}

function assertMutableProject(project: ProjectProjection): void {
  assertInspectableProject(project);
  if (project.accessMode !== "read-write") throw new Error("RO-CORE-MUTATION-UNAVAILABLE");
}

export class ControlledRecalculationCoordinator {
  private readonly scheduleAttempts = new Map<string, { readonly idempotencyKey: string; readonly requestedAt: string }>();
  private readonly restoreReviewAttempts = new Map<string, { readonly idempotencyKey: string; readonly requestedAt: string }>();
  private readonly restoreAttempts = new Map<string, { readonly modifiedAt: string }>();

  constructor(
    private readonly client: CoreApiClient,
    private readonly createCommandId: () => string = commandId,
    private readonly now: () => string = () => new Date().toISOString(),
  ) {}

  async loadAcceptedIntent(project: ProjectProjection): Promise<IntentDraftProjection | null> {
    assertInspectableProject(project);
    return acceptedRecalculationIntent(await this.client.intent({ root: project.root }));
  }

  async preview(project: ProjectProjection, targetRevisionId: string): Promise<RecalculationPreview> {
    assertInspectableProject(project, targetRevisionId);
    const preview = await this.client.previewRecalculation({ root: project.root, targetRevisionId });
    if (preview.projectId !== project.projectId) throw new Error("RO-CORE-RESPONSE-INVALID");
    return preview;
  }

  async schedule(
    project: ProjectProjection,
    preview: RecalculationPreview,
    intent: IntentDraftProjection,
    changeId: string,
  ): Promise<RecalculationScheduleProjection> {
    assertMutableProject(project);
    if (preview.projectId !== project.projectId || intent.status !== "accepted"
      || !preview.changeIds.includes(changeId) || !UUID_V7.test(changeId)) {
      throw new Error("RO-CORE-REQUEST-INVALID");
    }
    const authorityKey = [project.projectId, preview.targetRevisionId, preview.planSha256, changeId,
      intent.intentId, intent.revisionId, intent.revisionContentHash].join(":");
    let attempt = this.scheduleAttempts.get(authorityKey);
    if (!attempt) {
      attempt = { idempotencyKey: this.createCommandId(), requestedAt: this.now() };
      this.scheduleAttempts.set(authorityKey, attempt);
    }
    return await this.client.scheduleRecalculation({
      root: project.root,
      targetRevisionId: preview.targetRevisionId,
      changeId,
      expectedPlanSha256: preview.planSha256,
      intentId: intent.intentId,
      intentRevisionId: intent.revisionId,
      intentSha256: intent.revisionContentHash,
      requestedAt: attempt.requestedAt,
    }, attempt.idempotencyKey);
  }

  async compare(
    project: ProjectProjection,
    beforeRevisionId: string,
    afterRevisionId: string,
  ): Promise<RecalculationComparisonProjection> {
    assertInspectableProject(project, beforeRevisionId);
    if (!UUID_V7.test(afterRevisionId) || beforeRevisionId === afterRevisionId) {
      throw new Error("RO-CORE-REQUEST-INVALID");
    }
    return await this.client.compareRecalculation({ root: project.root, beforeRevisionId, afterRevisionId });
  }

  async requestRestoreReview(
    project: ProjectProjection,
    intent: IntentDraftProjection,
    beforeRevisionId: string,
    afterRevisionId: string,
  ): Promise<RecalculationRestoreReviewProjection> {
    assertMutableProject(project);
    if (intent.status !== "accepted" || !UUID_V7.test(beforeRevisionId) || !UUID_V7.test(afterRevisionId)
      || beforeRevisionId === afterRevisionId) throw new Error("RO-CORE-REQUEST-INVALID");
    const authorityKey = [project.projectId, beforeRevisionId, afterRevisionId,
      intent.intentId, intent.revisionId, intent.revisionContentHash].join(":");
    let attempt = this.restoreReviewAttempts.get(authorityKey);
    if (!attempt) {
      attempt = { idempotencyKey: this.createCommandId(), requestedAt: this.now() };
      this.restoreReviewAttempts.set(authorityKey, attempt);
    }
    return await this.client.requestRecalculationRestoreReview({
      root: project.root,
      beforeRevisionId,
      afterRevisionId,
      intentId: intent.intentId,
      intentRevisionId: intent.revisionId,
      intentSha256: intent.revisionContentHash,
      requestedAt: attempt.requestedAt,
    }, attempt.idempotencyKey);
  }

  async restore(
    project: ProjectProjection,
    review: RecalculationRestoreReviewProjection,
    priorAdjudicatedRevisionId: string,
    expectedCurrentRevisionId: string,
    decisionId: string,
  ): Promise<RecalculationRestoredRevision> {
    assertMutableProject(project);
    if (!UUID_V7.test(review.workflowRunId) || !UUID_V7.test(review.humanTaskId)
      || !UUID_V7.test(priorAdjudicatedRevisionId) || !UUID_V7.test(expectedCurrentRevisionId)
      || !UUID_V7.test(decisionId) || priorAdjudicatedRevisionId === expectedCurrentRevisionId) {
      throw new Error("RO-CORE-REQUEST-INVALID");
    }
    const authorityKey = [project.projectId, review.workflowRunId, review.humanTaskId, decisionId,
      priorAdjudicatedRevisionId, expectedCurrentRevisionId].join(":");
    let attempt = this.restoreAttempts.get(authorityKey);
    if (!attempt) {
      attempt = { modifiedAt: this.now() };
      this.restoreAttempts.set(authorityKey, attempt);
    }
    return await this.client.restoreRecalculationRevision({
      root: project.root,
      workflowRunId: review.workflowRunId,
      humanTaskId: review.humanTaskId,
      decisionId,
      priorAdjudicatedRevisionId,
      expectedCurrentRevisionId,
      modifiedAt: attempt.modifiedAt,
    });
  }
}

type LineageDirection = ProvenanceLineageRequest["direction"];
type LineageNodeRole =
  | "Selected output"
  | "Prior same-entity revision"
  | "Upstream source or alternate"
  | "Later same-entity revision"
  | "Downstream output"
  | "Source use"
  | "Invalidation or stale fact";

export interface AuditLineageWorkspaceProps {
  readonly project: ProjectProjection | null;
  readonly announce: (message: string) => void;
  readonly transport?: CoreApiTransport;
  readonly initialRevisionId?: string;
  readonly initialTrace?: ProvenanceLineagePage | null;
}

export function lineageAvailability(project: ProjectProjection | null): {
  readonly available: boolean;
  readonly reason: string | null;
} {
  if (!project) return { available: false, reason: "Open a local project to trace lineage." };
  if (!project.open || project.accessMode === "closed") {
    return { available: false, reason: "Open this project before tracing lineage." };
  }
  return { available: true, reason: null };
}

export function provenanceLineageRequest(
  project: ProjectProjection,
  revisionId: string,
  direction: LineageDirection,
  cursor: number,
): ProvenanceLineageRequest {
  if (!lineageAvailability(project).available || !UUID_V7.test(revisionId)
    || (direction !== "ancestors" && direction !== "descendants")
    || !Number.isInteger(cursor) || cursor < 0 || cursor > 10_000) {
    throw new Error("RO-CORE-REQUEST-INVALID");
  }
  return {
    root: project.root,
    revisionId,
    direction,
    cursor,
    pageSize: PAGE_SIZE,
    maxDepth: MAX_DEPTH,
  };
}

export function continuationLineageRequest(
  accepted: ProvenanceLineageRequest,
  cursor: number,
): ProvenanceLineageRequest {
  if (accepted.cursor !== 0 || !Number.isInteger(cursor) || cursor <= 0 || cursor > 10_000) {
    throw new Error("RO-CORE-REQUEST-INVALID");
  }
  return { ...accepted, cursor };
}

export async function loadLineagePage(
  client: ReturnType<typeof createCoreApiClient>,
  project: ProjectProjection,
  revisionId: string,
  direction: LineageDirection,
  cursor: number,
  accepted: ProvenanceLineageRequest | null = null,
): Promise<{ readonly request: ProvenanceLineageRequest; readonly page: ProvenanceLineagePage }> {
  if ((accepted === null && cursor !== 0) || (accepted !== null && cursor === 0)) {
    throw new Error("RO-CORE-REQUEST-INVALID");
  }
  const request = accepted === null
    ? provenanceLineageRequest(project, revisionId, direction, cursor)
    : continuationLineageRequest(accepted, cursor);
  return { request, page: await client.lineage(request) };
}

export function lineageNodeRole(
  node: ProvenanceLineageNode,
  selected: ProvenanceLineageNode | undefined,
  direction: LineageDirection,
): LineageNodeRole {
  if (node.relationType === "wasInvalidatedBy") return "Invalidation or stale fact";
  if (node.relationType === "used") return "Source use";
  if (node.depth === 0 && node.revisionId === selected?.revisionId) return "Selected output";
  if (direction === "ancestors") {
    return selected && node.entityId === selected.entityId
      ? "Prior same-entity revision"
      : "Upstream source or alternate";
  }
  return selected && node.entityId === selected.entityId
    ? "Later same-entity revision"
    : "Downstream output";
}

function lineageNodeState(node: ProvenanceLineageNode): string {
  if (node.relationType === "wasInvalidatedBy" || node.knowledgeStatus === "stale") return "Stale or invalidated";
  if (node.depth === 0) return "Current selection";
  return "Historical";
}

function safeFailure(error: unknown): { readonly title: string; readonly message: string } {
  if (error instanceof CoreApiClientError) {
    return {
      title: `${error.problem.title} (${error.problem.code})`,
      message: `${error.problem.detail} ${error.problem.remediation}`,
    };
  }
  return {
    title: "RO-CORE-LOCAL-ACTION-FAILED",
    message: "The local Core action could not be verified. Existing revisions and decisions remain authoritative; check Core status and retry.",
  };
}

export function mergeLineagePage(
  current: ProvenanceLineagePage,
  next: ProvenanceLineagePage,
  requestedCursor: number,
): ProvenanceLineagePage {
  if (current.revisionId !== next.revisionId || current.direction !== next.direction
    || current.nextCursor !== requestedCursor
    || (next.nextCursor !== null && (
      next.items.length === 0
      || next.nextCursor <= requestedCursor
      || next.nextCursor !== requestedCursor + next.items.length
    ))
    || current.exportAllowed !== (current.exportDenialReason === null)
    || next.exportAllowed !== (next.exportDenialReason === null)
    || current.truncated !== (current.truncationReason !== null)
    || next.truncated !== (next.truncationReason !== null)) {
    throw new Error("RO-CORE-RESPONSE-INVALID");
  }
  const identities = new Set(current.items.map((item) => item.factId));
  const lastDepth = current.items.at(-1)?.depth ?? 0;
  if (next.items.some((item) => identities.has(item.factId))
    || (next.items[0]?.depth ?? lastDepth) < lastDepth) throw new Error("RO-CORE-RESPONSE-INVALID");
  const items = [...current.items, ...next.items];
  const missingRevisionIds = [...new Set([...current.missingRevisionIds, ...next.missingRevisionIds])];
  const legacyEventCount = Math.max(current.legacyEventCount, next.legacyEventCount);
  const truncationReason = current.truncationReason ?? next.truncationReason;
  const truncated = current.truncated || next.truncated;
  const integrityReview = current.integrityState === "integrity-review"
    || next.integrityState === "integrity-review"
    || current.exportDenialReason === "integrity-review"
    || next.exportDenialReason === "integrity-review"
    || truncated
    || missingRevisionIds.length > 0
    || legacyEventCount > 0;
  const rightsRestricted = current.exportDenialReason === "rights-restricted"
    || next.exportDenialReason === "rights-restricted"
    || items.some((item) => item.rightsStatus === "denied" || item.rightsStatus === "unknown");
  const exportDenialReason = integrityReview
    ? "integrity-review"
    : rightsRestricted
      ? "rights-restricted"
      : null;
  return {
    ...next,
    items,
    missingRevisionIds,
    truncated,
    truncationReason,
    integrityState: integrityReview ? "integrity-review" : "verified",
    legacyEventCount,
    exportAllowed: exportDenialReason === null,
    exportDenialReason,
  };
}

export function lineageManifestReady(
  trace: ProvenanceLineagePage,
  acceptedQuery: ProvenanceLineageRequest | null,
): boolean {
  return acceptedQuery !== null
    && acceptedQuery.cursor === 0
    && acceptedQuery.revisionId === trace.revisionId
    && acceptedQuery.direction === trace.direction
    && trace.nextCursor === null
    && !trace.truncated
    && trace.truncationReason === null
    && trace.integrityState === "verified"
    && trace.missingRevisionIds.length === 0
    && trace.legacyEventCount === 0
    && trace.exportAllowed
    && trace.exportDenialReason === null
    && !trace.items.some((item) => item.rightsStatus === "denied" || item.rightsStatus === "unknown");
}

export function exportLineageManifest(
  trace: ProvenanceLineagePage,
  acceptedQuery: ProvenanceLineageRequest | null,
): string {
  if (acceptedQuery === null || !lineageManifestReady(trace, acceptedQuery)) {
    throw new Error("RO-CORE-EXPORT-DENIED");
  }
  return JSON.stringify({
    schemaVersion: "1.0",
    manifestType: "content-minimized-lineage",
    completeness: "complete",
    revisionId: trace.revisionId,
    direction: trace.direction,
    acceptedBounds: {
      maxDepth: acceptedQuery.maxDepth,
      pageSize: acceptedQuery.pageSize,
      startCursor: 0,
      terminalCursor: trace.items.length,
    },
    integrityState: trace.integrityState,
    redaction: "research-content-and-raw-prompts-omitted",
    egressDecision: "local-file-only",
    items: trace.items,
  }, null, 2);
}

type RecalculationAction = "preview" | "schedule" | "compare" | "request-restore-review" | "restore";

interface ControlledRecalculationRegionProps {
  readonly project: ProjectProjection | null;
  readonly targetRevisionId: string;
  readonly trace: ProvenanceLineagePage | null;
  readonly coordinator: ControlledRecalculationCoordinator;
  readonly announce: (message: string) => void;
}

function ControlledRecalculationRegion({
  project,
  targetRevisionId,
  trace,
  coordinator,
  announce,
}: ControlledRecalculationRegionProps): ReactNode {
  const [preview, setPreview] = useState<RecalculationPreview | null>(null);
  const [intent, setIntent] = useState<IntentDraftProjection | null>(null);
  const [selectedChangeId, setSelectedChangeId] = useState("");
  const [deferred, setDeferred] = useState(false);
  const [schedule, setSchedule] = useState<RecalculationScheduleProjection | null>(null);
  const [beforeRevisionId, setBeforeRevisionId] = useState("");
  const [afterRevisionId, setAfterRevisionId] = useState("");
  const [comparison, setComparison] = useState<RecalculationComparisonProjection | null>(null);
  const [restoreReview, setRestoreReview] = useState<RecalculationRestoreReviewProjection | null>(null);
  const [decisionId, setDecisionId] = useState("");
  const [restored, setRestored] = useState<RecalculationRestoredRevision | null>(null);
  const [busy, setBusy] = useState<RecalculationAction | null>(null);
  const [failure, setFailure] = useState<{ readonly title: string; readonly message: string } | null>(null);

  useEffect(() => {
    setPreview(null);
    setIntent(null);
    setSelectedChangeId("");
    setDeferred(false);
    setSchedule(null);
    setBeforeRevisionId("");
    setAfterRevisionId("");
    setComparison(null);
    setRestoreReview(null);
    setDecisionId("");
    setRestored(null);
    setFailure(null);
  }, [project?.projectId, project?.root]);

  const mutable = project?.open === true
    && project.accessMode === "read-write"
    && project.compatibilityState === "compatible";
  const currentPreview = preview?.targetRevisionId === targetRevisionId;
  const exactComparison = comparison?.beforeRevisionId === beforeRevisionId
    && comparison.afterRevisionId === afterRevisionId;
  const validComparisonInput = UUID_V7.test(beforeRevisionId)
    && UUID_V7.test(afterRevisionId)
    && beforeRevisionId !== afterRevisionId;
  const selectedNode = trace?.items.find((node) => node.revisionId === targetRevisionId);

  const fail = (error: unknown, action: string): void => {
    const safe = safeFailure(error);
    setFailure(safe);
    announce(`${action} did not complete. ${safe.title}`);
  };

  const runPreview = async (): Promise<void> => {
    if (!project) return;
    setBusy("preview");
    setFailure(null);
    setIntent(null);
    try {
      const next = await coordinator.preview(project, targetRevisionId);
      setPreview(next);
      setSelectedChangeId(next.changeIds[0] ?? "");
      setDeferred(false);
      setSchedule(null);
      setBeforeRevisionId(next.targetRevisionId);
      setAfterRevisionId(next.replacementRevisionIds[0] ?? "");
      setComparison(null);
      setRestoreReview(null);
      setDecisionId("");
      setRestored(null);
      const accepted = await coordinator.loadAcceptedIntent(project);
      setIntent(accepted);
      announce(accepted
        ? "Controlled recalculation impact preview loaded and bound to the accepted research intent."
        : "Impact preview loaded. Scheduling remains unavailable until the research intent is accepted.");
    } catch (error) {
      fail(error, "Recalculation preview");
    } finally {
      setBusy(null);
    }
  };

  const runSchedule = async (): Promise<void> => {
    if (!project || !preview || !intent || !selectedChangeId || !currentPreview) return;
    setBusy("schedule");
    setFailure(null);
    try {
      const result = await coordinator.schedule(project, preview, intent, selectedChangeId);
      setSchedule(result);
      announce("Selected recalculation scheduled as a new immutable candidate; the stale revision remains visible.");
    } catch (error) {
      fail(error, "Recalculation schedule");
    } finally {
      setBusy(null);
    }
  };

  const runComparison = async (): Promise<void> => {
    if (!project) return;
    setBusy("compare");
    setFailure(null);
    try {
      const result = await coordinator.compare(project, beforeRevisionId, afterRevisionId);
      setComparison(result);
      setRestoreReview(null);
      setDecisionId("");
      setRestored(null);
      announce("Immutable before-and-after revision comparison loaded.");
    } catch (error) {
      fail(error, "Revision comparison");
    } finally {
      setBusy(null);
    }
  };

  const runRestoreReview = async (): Promise<void> => {
    if (!project || !intent || !exactComparison) return;
    setBusy("request-restore-review");
    setFailure(null);
    try {
      const result = await coordinator.requestRestoreReview(
        project,
        intent,
        beforeRevisionId,
        afterRevisionId,
      );
      setRestoreReview(result);
      setDecisionId("");
      setRestored(null);
      announce("Restore review requested. No revision was activated; an authorized human decision is required.");
    } catch (error) {
      fail(error, "Restore review request");
    } finally {
      setBusy(null);
    }
  };

  const runRestore = async (): Promise<void> => {
    if (!project || !restoreReview || !exactComparison) return;
    setBusy("restore");
    setFailure(null);
    try {
      const result = await coordinator.restore(
        project,
        restoreReview,
        beforeRevisionId,
        afterRevisionId,
        decisionId,
      );
      setRestored(result);
      announce("The recorded human decision created a new restoration revision; prior revisions remain immutable.");
    } catch (error) {
      fail(error, "Revision restoration");
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="controlled-recalculation ro-stack" aria-labelledby="controlled-recalculation-title">
      <div className="lineage-results-heading ro-cluster">
        <Typography id="controlled-recalculation-title" as="h2" variant="section-title">
          Controlled recalculation
        </Typography>
        <span>Preview first; preserve every adjudicated revision.</span>
      </div>

      <section className="lineage-notice ro-notice" data-recalculation-stale aria-labelledby="recalculation-stale-title">
        <strong id="recalculation-stale-title">
          {preview ? "Stale output remains visible" : "Check an output for dependency changes"}
        </strong>
        {preview ? (
          <>
            <span>{preview.causes[0]?.reason ?? "Core found a material dependency change for this revision."}</span>
            <span>
              Safest next action: inspect the bounded impact classes, then schedule only the selected change.
              {deferred ? " Recalculation is deferred; staleness has not been cleared." : ""}
            </span>
          </>
        ) : (
          <span>Enter an exact revision ID and preview its current dependency impact. No work is scheduled by preview.</span>
        )}
        <Button
          onClick={() => { void runPreview(); }}
          tone="primary"
          disabled={!project || busy !== null || !UUID_V7.test(targetRevisionId)}
          data-preview-recalculation
        >
          {busy === "preview" ? "Previewing…" : "Preview impacts"}
        </Button>
      </section>

      {failure ? (
        <div className="lineage-notice ro-notice lineage-notice--danger" role="alert">
          <strong>{failure.title}</strong><span>{failure.message}</span>
        </div>
      ) : null}

      <section className="lineage-governed-region ro-card ro-stack" data-recalculation-preview aria-labelledby="recalculation-preview-title">
        <div className="lineage-results-heading ro-cluster">
          <Typography id="recalculation-preview-title" as="h3" variant="section-title">Impact preview</Typography>
          <StatusBadge tone={preview ? "warning" : "neutral"}>
            {preview ? `${preview.causes.length} affected` : "Not previewed"}
          </StatusBadge>
        </div>
        {preview ? (
          <>
            {!currentPreview ? <p role="alert">The revision ID changed after this preview. Preview again before scheduling.</p> : null}
            <div className="lineage-table-scroll ro-table-region" tabIndex={0} aria-label="Recalculation impact table scroll region">
              <table>
                <caption>Core-classified effects for the exact preview plan</caption>
                <thead><tr><th scope="col">Class</th><th scope="col">Affected identity</th><th scope="col">Reason</th><th scope="col">Action</th></tr></thead>
                <tbody>
                  {preview.causes.map((cause) => {
                    const impactClass = recalculationImpactClass(cause);
                    return (
                      <tr key={cause.causeId} data-impact-state={impactClass}>
                        <td><StatusBadge tone={impactClass === "automatic" ? "success" : impactClass === "blocked" ? "danger" : "warning"}>{impactClass.replace("-", " ")}</StatusBadge></td>
                        <td><code>{cause.causeId}</code><span>depth {cause.depth} · {cause.confidence}</span></td>
                        <td>{cause.reason}</td>
                        <td>{impactClass === "blocked" ? "Preserve stale revision" : impactClass === "review-required" ? "Create candidate for review" : "Eligible for selected recalculation"}</td>
                      </tr>
                    );
                  })}
                  {preview.reusableRevisionIds.map((revision) => (
                    <tr key={`reuse:${revision}`} data-impact-state="informational-reuse">
                      <td><StatusBadge tone="info">informational</StatusBadge></td>
                      <td><code>{revision}</code></td>
                      <td>Core proved this revision unchanged under the exact plan.</td>
                      <td>Reuse without recomputation</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <label htmlFor="recalculation-change-id">Selected bounded change</label>
            <select id="recalculation-change-id" value={selectedChangeId} onChange={(event) => setSelectedChangeId(event.currentTarget.value)}>
              {preview.changeIds.map((changeId) => <option key={changeId} value={changeId}>{changeId}</option>)}
            </select>
            <div className="lineage-action-row ro-action-row">
              <Button
                onClick={() => {
                  setDeferred(true);
                  announce("Recalculation deferred; the stale state remains visible.");
                }}
                disabled={busy !== null || !preview.deferPreservesStaleVisibility}
                data-defer-recalculation
              >Defer and keep stale</Button>
              <Button
                onClick={() => { void runSchedule(); }}
                tone="primary"
                disabled={busy !== null || !mutable || !intent || !selectedChangeId || !currentPreview || schedule !== null}
                data-schedule-recalculation
              >{busy === "schedule" ? "Scheduling…" : "Schedule selected"}</Button>
            </div>
            {!intent ? <p role="status">An accepted research intent is required before scheduling or restore review.</p> : null}
            {!mutable ? <p role="status">Read-only inspection is available, but recalculation and restoration require compatible read-write project access.</p> : null}
            {schedule ? <p role="status">Candidate workflow <code>{schedule.workflowRunId}</code> is {schedule.state}; job <code>{schedule.jobId}</code>. The active revision was not overwritten.</p> : null}
          </>
        ) : (
          <>
            <p>Preview an exact revision to see automatic, review-required, blocked, and informational effects.</p>
            <div className="lineage-action-row ro-action-row">
              <Button disabled data-defer-recalculation>Defer and keep stale</Button>
              <Button disabled data-schedule-recalculation>Schedule selected</Button>
            </div>
          </>
        )}
      </section>

      <section className="lineage-governed-region ro-card ro-stack" data-recalculation-policy aria-labelledby="recalculation-policy-title">
        <Typography id="recalculation-policy-title" as="h3" variant="section-title">Current policy and rights authority</Typography>
        <dl className="lineage-identity">
          <div><dt>Preview policy</dt><dd>{preview ? <code>{preview.policySha256}</code> : "Not evaluated"}</dd></div>
          <div><dt>Selected output rights</dt><dd>{selectedNode ? selectedNode.rightsStatus : "Load lineage for the exact rights result"}</dd></div>
          <div><dt>Egress</dt><dd>No remote egress is authorized by these controls.</dd></div>
        </dl>
        <p>Core re-evaluates current policy when work is scheduled and when restore review is requested.</p>
      </section>

      <section className="lineage-governed-region ro-card ro-stack" data-recalculation-comparison aria-labelledby="recalculation-comparison-title">
        <Typography id="recalculation-comparison-title" as="h3" variant="section-title">Immutable revision comparison</Typography>
        <p>Compare the current adjudicated revision with a generated candidate. Neither revision is modified.</p>
        <div className="recalculation-revision-fields ro-grid ro-form">
          <label htmlFor="recalculation-before-id">Before revision ID</label>
          <input id="recalculation-before-id" value={beforeRevisionId} onChange={(event) => {
            setBeforeRevisionId(event.currentTarget.value.trim().toLowerCase());
            setRestoreReview(null); setDecisionId(""); setRestored(null);
          }} autoComplete="off" spellCheck={false} />
          <label htmlFor="recalculation-after-id">Candidate/current revision ID</label>
          <input id="recalculation-after-id" value={afterRevisionId} onChange={(event) => {
            setAfterRevisionId(event.currentTarget.value.trim().toLowerCase());
            setRestoreReview(null); setDecisionId(""); setRestored(null);
          }} autoComplete="off" spellCheck={false} />
        </div>
        <Button onClick={() => { void runComparison(); }} disabled={!project || busy !== null || !validComparisonInput} data-compare-recalculation>
          {busy === "compare" ? "Comparing…" : "Compare revisions"}
        </Button>
        {comparison ? (
          <dl className="lineage-identity">
            <div><dt>Aggregate</dt><dd><code>{comparison.aggregateId}</code></dd></div>
            <div><dt>Before</dt><dd>revision {comparison.beforeRevision} · <code>{comparison.beforeRevisionId}</code></dd></div>
            <div><dt>After</dt><dd>revision {comparison.afterRevision} · <code>{comparison.afterRevisionId}</code></dd></div>
            <div><dt>Changed fields</dt><dd>{comparison.changedFields.length ? comparison.changedFields.join(", ") : "No field changes"}</dd></div>
          </dl>
        ) : null}
      </section>

      <section className="lineage-governed-region ro-card ro-stack" data-recalculation-restoration aria-labelledby="recalculation-restoration-title">
        <div className="lineage-results-heading ro-cluster">
          <Typography id="recalculation-restoration-title" as="h3" variant="section-title">Human-gated restoration</Typography>
          <StatusBadge tone={restoreReview ? "warning" : "neutral"}>{restoreReview ? "Decision required" : "Review not requested"}</StatusBadge>
        </div>
        <p>Requesting review does not activate a revision. Approval creates a new restoration revision and never rewrites history.</p>
        <Button
          onClick={() => { void runRestoreReview(); }}
          disabled={busy !== null || !mutable || !intent || !exactComparison || restoreReview !== null}
          data-request-restore-review
        >{busy === "request-restore-review" ? "Requesting…" : "Request restore review"}</Button>
        {restoreReview ? (
          <>
            <dl className="lineage-identity">
              <div><dt>Workflow</dt><dd><code>{restoreReview.workflowRunId}</code></dd></div>
              <div><dt>Human task</dt><dd><code>{restoreReview.humanTaskId}</code></dd></div>
              <div><dt>Policy</dt><dd><code>{restoreReview.policySha256}</code></dd></div>
            </dl>
            <label htmlFor="recalculation-decision-id">Recorded approved decision ID from Task Center</label>
            <input id="recalculation-decision-id" value={decisionId} onChange={(event) => setDecisionId(event.currentTarget.value.trim().toLowerCase())} autoComplete="off" spellCheck={false} />
            <Button
              onClick={() => { void runRestore(); }}
              tone="primary"
              disabled={busy !== null || !mutable || !exactComparison || !UUID_V7.test(decisionId) || restored !== null}
              data-restore-revision
            >{busy === "restore" ? "Restoring…" : "Create restoration revision"}</Button>
          </>
        ) : (
          <>
            <input aria-label="Recorded approved decision ID from Task Center" value="" disabled readOnly />
            <Button disabled data-restore-revision>Create restoration revision</Button>
          </>
        )}
        {restored ? <p role="status">Restoration revision <code>{restored.revisionId}</code> was created at revision {restored.revision}; rights {restored.rightsStatus}.</p> : null}
      </section>
    </section>
  );
}

export function AuditLineageWorkspace({
  project,
  announce,
  transport = packagedProjectTransport,
  initialRevisionId = "",
  initialTrace = null,
}: AuditLineageWorkspaceProps): ReactNode {
  const client = useMemo(() => createCoreApiClient(transport), [transport]);
  const recalculationCoordinator = useMemo(() => new ControlledRecalculationCoordinator(client), [client]);
  const availability = lineageAvailability(project);
  const [revisionId, setRevisionId] = useState(initialRevisionId);
  const [direction, setDirection] = useState<LineageDirection>(initialTrace?.direction ?? "ancestors");
  const [trace, setTrace] = useState<ProvenanceLineagePage | null>(initialTrace);
  const [traceQuery, setTraceQuery] = useState<ProvenanceLineageRequest | null>(
    initialTrace && project ? provenanceLineageRequest(project, initialTrace.revisionId, initialTrace.direction, 0) : null,
  );
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<{ readonly title: string; readonly message: string } | null>(null);

  useEffect(() => {
    setRevisionId("");
    setTrace(null);
    setTraceQuery(null);
    setFailure(null);
  }, [project?.projectId]);

  const runTrace = async (cursor: number, append: boolean): Promise<void> => {
    if (!project) return;
    setBusy(true);
    setFailure(null);
    try {
      const result = await loadLineagePage(
        client,
        project,
        revisionId,
        direction,
        cursor,
        append ? traceQuery : null,
      );
      const request = result.request;
      const next = result.page;
      setTrace((current) => append && current ? mergeLineagePage(current, next, cursor) : next);
      if (!append) setTraceQuery({ ...request, cursor: 0 });
      announce(append ? "More lineage records loaded." : "Exact output lineage traced.");
    } catch (error) {
      const safe = safeFailure(error);
      setFailure(safe);
      announce(`Lineage trace did not complete. ${safe.title}`);
    } finally {
      setBusy(false);
    }
  };

  const submit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    void runTrace(0, false);
  };
  const selected = trace?.items.find((item) => item.depth === 0);
  const validRevision = UUID_V7.test(revisionId);
  const humanDecisions = trace?.items.filter(
    (item) => item.entityKind === "decision" && item.agentType === "human",
  ) ?? [];
  const manifestReady = trace ? lineageManifestReady(trace, traceQuery) : false;
  const downloadManifest = (): void => {
    if (!trace) return;
    try {
      const payload = exportLineageManifest(trace, traceQuery);
      const url = URL.createObjectURL(new Blob([payload], { type: "application/json" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `lineage-${trace.revisionId}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      announce("Content-minimized lineage manifest exported locally.");
    } catch {
      announce("Lineage export remains denied by integrity or rights policy.");
    }
  };

  return (
    <section className="audit-lineage-workspace ro-page-region" aria-labelledby="audit-lineage-title" data-audit-lineage-workspace>
      <div className="page-header">
        <Typography id="audit-lineage-title" as="h1" variant="page-title">Audit &amp; lineage</Typography>
        <Typography className="page-subtitle">
          Trace exact output lineage, inspect dependency impacts, and govern selective recalculation through immutable revisions and explicit human decisions.
        </Typography>
      </div>

      {!availability.available ? (
        <Panel title="Lineage unavailable">
          <p role="status">{availability.reason}</p>
          <p>No project content or identifiers are requested while this boundary is unavailable.</p>
        </Panel>
      ) : (
        <form className="lineage-trace-form ro-card ro-form" onSubmit={submit}>
          <label htmlFor="lineage-revision-id">Exact output revision ID</label>
          <input
            id="lineage-revision-id"
            value={revisionId}
            onChange={(event) => setRevisionId(event.currentTarget.value.trim().toLowerCase())}
            pattern="[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
            maxLength={36}
            autoComplete="off"
            spellCheck={false}
            aria-describedby="lineage-revision-help"
            required
          />
          <span id="lineage-revision-help" className="field-note">
            Use the immutable UUIDv7 attached to the synthesis sentence, evidence field, claim, or other output.
          </span>
          <label htmlFor="lineage-direction">Trace direction</label>
          <select
            id="lineage-direction"
            value={direction}
            onChange={(event) => setDirection(event.currentTarget.value as LineageDirection)}
          >
            <option value="ancestors">Sources and prior transformations</option>
            <option value="descendants">Downstream outputs and decisions</option>
          </select>
          <Button type="submit" tone="primary" disabled={busy || !validRevision} data-trace-lineage>
            {busy ? "Tracing…" : "Trace lineage"}
          </Button>
        </form>
      )}

      {failure ? (
        <div className="lineage-notice ro-notice lineage-notice--danger" role="alert">
          <strong>{failure.title}</strong>
          <span>{failure.message}</span>
        </div>
      ) : null}

      <ControlledRecalculationRegion
        project={project}
        targetRevisionId={revisionId}
        trace={trace}
        coordinator={recalculationCoordinator}
        announce={announce}
      />

      {trace ? (
        <>
          <div className="lineage-summary-grid ro-grid">
            <Panel title="Output identity">
              <dl className="lineage-identity">
                <div><dt>Revision</dt><dd><code>{trace.revisionId}</code></dd></div>
                <div><dt>Direction</dt><dd>{trace.direction}</dd></div>
                <div><dt>Records shown</dt><dd>{trace.items.length}</dd></div>
              </dl>
            </Panel>
            <Panel title="Provenance completeness">
              <StatusBadge tone={trace.integrityState === "verified" ? "success" : "warning"}>
                {trace.integrityState === "verified" ? "Verified" : "Integrity review required"}
              </StatusBadge>
              <p>{trace.legacyEventCount} legacy {trace.legacyEventCount === 1 ? "event" : "events"} remain visibly identified.</p>
            </Panel>
          </div>

          {trace.integrityState === "integrity-review" ? (
            <div className="lineage-notice ro-notice" role="alert">
              <strong>Integrity review required</strong>
              <span>Keep this trace available for inspection, but do not rely on it for export or claim use until repaired.</span>
            </div>
          ) : null}

          {trace.truncated ? (
            <div className="lineage-notice ro-notice" role="alert" data-lineage-truncated>
              <strong>Lineage trace is incomplete</strong>
              <span>
                The bounded local query reached its {trace.truncationReason === "scan-limit" ? "scan" : "continuation"} limit.
                Returned facts remain available for inspection, but complete manifest export is denied.
              </span>
            </div>
          ) : null}

          {trace.missingRevisionIds.length ? (
            <div className="lineage-notice ro-notice" role="alert">
              <strong>Referenced revisions are missing</strong>
              <ul>{trace.missingRevisionIds.map((item) => <li key={item}><code>{item}</code></li>)}</ul>
            </div>
          ) : null}

          <section className="lineage-results ro-stack" aria-labelledby="lineage-results-title">
            <div className="lineage-results-heading ro-cluster">
              <Typography id="lineage-results-title" as="h2" variant="section-title">Lineage trace</Typography>
              <span>{trace.items.length === 0 ? "No canonical lineage record found." : "All returned branches remain visible."}</span>
            </div>
            {trace.items.length ? (
              <div className="lineage-table-scroll ro-table-region" tabIndex={0} aria-label="Audit lineage table scroll region">
                <table>
                  <caption>Exact, content-free provenance facts discovered by the wasDerivedFrom {trace.direction} traversal for the selected output revision</caption>
                  <thead><tr><th scope="col">Relation and state</th><th scope="col">Entity revision</th><th scope="col">Transformation and configuration</th><th scope="col">Responsible actor</th><th scope="col">Audit event</th></tr></thead>
                  <tbody>
                    {trace.items.map((node) => (
                      <tr key={node.factId}>
                        <td><strong>{lineageNodeRole(node, selected, trace.direction)}</strong><span>{lineageNodeState(node)} · depth {node.depth}</span></td>
                        <td><span>{node.entityKind} · {node.entityDirection}</span><code>{node.entityId}</code><code>{node.revisionId}</code>{node.relatedRevisionId ? <code>{node.relatedRevisionId}</code> : null}</td>
                        <td><span>{node.activityType} · {node.activityStatus}</span><code>{node.activityId}</code><span>{node.configurationId} · {node.configurationVersion}</span><code>{node.configurationHash}</code></td>
                        <td><span>{node.agentType} · {node.agentRole}</span><code>{node.agentId}</code></td>
                        <td><span>{node.relationType} · {node.eventType}</span><code>{node.eventId}</code><time dateTime={node.occurredAt}>{node.occurredAt}</time></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            {trace.nextCursor !== null ? (
              <Button disabled={busy} onClick={() => { void runTrace(trace.nextCursor ?? 0, true); }}>
                {busy ? "Loading…" : "Load more lineage"}
              </Button>
            ) : null}
          </section>

          <section className="lineage-governed-region ro-card ro-stack" aria-labelledby="lineage-audit-events-title" data-audit-events>
            <Typography id="lineage-audit-events-title" as="h2" variant="section-title">Audit events</Typography>
            <p>Content-minimized security, model, scholarly, rights, and invalidation facts returned by Core.</p>
            <ol>{trace.items.map((node) => <li key={`audit:${node.factId}`}><code>{node.eventId}</code> {node.eventType} · {node.activityStatus} · <time dateTime={node.occurredAt}>{node.occurredAt}</time></li>)}</ol>
          </section>

          <section className="lineage-governed-region ro-card ro-stack" aria-labelledby="lineage-rights-title" data-rights-egress>
            <Typography id="lineage-rights-title" as="h2" variant="section-title">Rights &amp; egress decisions</Typography>
            <ul>{trace.items.map((node) => <li key={`rights:${node.factId}`}><code>{node.revisionId}</code> · rights {node.rightsStatus}</li>)}</ul>
            <p>Local manifest export: {manifestReady ? "allowed" : trace.exportAllowed && trace.nextCursor !== null ? "pending (load every lineage page)" : `denied (${trace.exportDenialReason})`}. This trace does not authorize remote egress.</p>
          </section>

          <section className="lineage-governed-region ro-card ro-stack" aria-labelledby="lineage-decisions-title" data-human-decisions>
            <Typography id="lineage-decisions-title" as="h2" variant="section-title">Human decisions</Typography>
            {humanDecisions.length ? <ul>{humanDecisions.map((node) => <li key={`decision:${node.factId}`}>{node.agentRole} · <code>{node.agentId}</code> · {node.eventType}</li>)}</ul> : <p>No human decision is recorded in this trace.</p>}
          </section>

          <section className="lineage-governed-region ro-card ro-stack" aria-labelledby="lineage-export-title" data-export-manifest>
            <Typography id="lineage-export-title" as="h2" variant="section-title">Exportable manifest</Typography>
            <p>Local JSON omits research content, raw prompts, secrets, and hidden rationale. Exact identities and policy states remain.</p>
            <Button onClick={downloadManifest} disabled={!manifestReady}>Export content-minimized manifest</Button>
            {trace.exportAllowed && trace.nextCursor !== null
              ? <p role="status">Load every lineage page before exporting the complete manifest.</p>
              : !manifestReady
                ? <p role="alert">Export denied: {trace.exportDenialReason === "integrity-review" ? "integrity review is required" : "one or more lineage targets are rights-restricted"}.</p>
                : null}
          </section>

          <div className="lineage-transparency-note ro-notice">
            <strong>Useful transparency</strong>
            <p>
              This view exposes exact sources, transformations, configuration or prompt-version identities, model or human roles,
              alternatives, decisions, and stale state—not hidden model rationale or chain-of-thought. Raw prompts and research text
              remain behind their governed content and rights boundaries.
            </p>
          </div>
        </>
      ) : null}
    </section>
  );
}
