import { readFileSync } from "node:fs";

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  createCoreApiClient,
  type CoreApiRequest,
  type IntentDraftProjection,
  type ProjectProjection,
  type ProvenanceLineagePage,
  type RecalculationPreview,
} from "@research-observatory/contracts/core-api";

import {
  AuditLineageWorkspace,
  ControlledRecalculationCoordinator,
  acceptedRecalculationIntent,
  continuationLineageRequest,
  exportLineageManifest,
  lineageManifestReady,
  lineageAvailability,
  lineageNodeRole,
  loadLineagePage,
  mergeLineagePage,
  provenanceLineageRequest,
  recalculationImpactClass,
} from "./AuditLineageWorkspace";

const project: ProjectProjection = {
  schemaVersion: "1.0",
  projectId: "6f93073a-5af0-47ef-b9cf-d5027e0ded99",
  displayName: "Local study",
  templateId: "theory-synthesis",
  lifecycleState: "active",
  root: "C:/Research/study-one",
  open: true,
  revision: 4,
  accessMode: "read-write",
  compatibilityState: "compatible",
  packageFormatVersion: "1.0.0",
  backupRequiredBeforeRepair: false,
  recoveryAction: "none",
  deleteConfirmation: "delete:6f93073a-5af0-47ef-b9cf-d5027e0ded99",
};

const lineage: ProvenanceLineagePage = {
  schemaVersion: "1.0",
  revisionId: "01890f47-eae3-7cc0-98c4-dc0c0c073981",
  direction: "ancestors",
  items: [
    {
      factId: "01890f47-eae3-7cc0-98c4-dc0c0c073980",
      relationType: "wasDerivedFrom",
      entityDirection: "output",
      revisionId: "01890f47-eae3-7cc0-98c4-dc0c0c073981",
      entityId: "01890f47-eae3-7cc0-88c4-dc0c0c073982",
      entityKind: "synthesis.sentence",
      relatedRevisionId: "01890f47-eae3-7cc0-98c4-dc0c0c07398a",
      knowledgeStatus: "inferred",
      rightsStatus: "allowed",
      depth: 0,
      eventId: "01890f47-eae3-7cc0-98c4-dc0c0c073983",
      eventType: "org.research-observatory.synthesis.created.v1",
      activityId: "01890f47-eae3-7cc0-98c4-dc0c0c073984",
      activityType: "synthesis.insert",
      activityStatus: "succeeded",
      configurationId: "model.synthesis-prompt",
      configurationVersion: "3.2.0",
      configurationHash: `sha256:${"1".repeat(64)}`,
      agentId: "01890f47-eae3-7cc0-98c4-dc0c0c073985",
      agentType: "model",
      agentRole: "synthesis.writer",
      occurredAt: "2026-08-29T19:00:00Z",
    },
    {
      factId: "01890f47-eae3-7cc0-98c4-dc0c0c073990",
      relationType: "wasInvalidatedBy",
      entityDirection: "input",
      revisionId: "01890f47-eae3-7cc0-98c4-dc0c0c073986",
      entityId: "01890f47-eae3-7cc0-88c4-dc0c0c073982",
      entityKind: "synthesis.sentence",
      relatedRevisionId: null,
      knowledgeStatus: "stale",
      rightsStatus: "allowed",
      depth: 1,
      eventId: "01890f47-eae3-7cc0-98c4-dc0c0c073987",
      eventType: "org.research-observatory.synthesis.invalidated.v1",
      activityId: "01890f47-eae3-7cc0-98c4-dc0c0c073988",
      activityType: "synthesis.revise",
      activityStatus: "succeeded",
      configurationId: "decision.revision",
      configurationVersion: "1.0.0",
      configurationHash: `sha256:${"2".repeat(64)}`,
      agentId: "01890f47-eae3-7cc0-98c4-dc0c0c073989",
      agentType: "human",
      agentRole: "claim.reviewer",
      occurredAt: "2026-08-29T18:00:00Z",
    },
    {
      factId: "01890f47-eae3-7cc0-98c4-dc0c0c073991",
      relationType: "wasGeneratedBy",
      entityDirection: "output",
      revisionId: "01890f47-eae3-7cc0-98c4-dc0c0c07398a",
      entityId: "01890f47-eae3-7cc0-88c4-dc0c0c07398b",
      entityKind: "evidence.passage",
      relatedRevisionId: null,
      knowledgeStatus: "verified",
      rightsStatus: "allowed",
      depth: 1,
      eventId: "01890f47-eae3-7cc0-98c4-dc0c0c07398c",
      eventType: "org.research-observatory.evidence.recorded.v1",
      activityId: "01890f47-eae3-7cc0-98c4-dc0c0c07398d",
      activityType: "evidence.extract",
      activityStatus: "succeeded",
      configurationId: "extract.evidence-passage",
      configurationVersion: "2.1.0",
      configurationHash: `sha256:${"3".repeat(64)}`,
      agentId: "01890f47-eae3-7cc0-98c4-dc0c0c07398e",
      agentType: "software",
      agentRole: "evidence.extractor",
      occurredAt: "2026-08-29T17:00:00Z",
    },
    {
      factId: "01890f47-eae3-7cc0-98c4-dc0c0c073992",
      relationType: "wasGeneratedBy",
      entityDirection: "output",
      revisionId: "01890f47-eae3-7cc0-98c4-dc0c0c073993",
      entityId: "01890f47-eae3-7cc0-88c4-dc0c0c073994",
      entityKind: "decision",
      relatedRevisionId: null,
      knowledgeStatus: "adjudicated",
      rightsStatus: "allowed",
      depth: 1,
      eventId: "01890f47-eae3-7cc0-98c4-dc0c0c073995",
      eventType: "org.research-observatory.decision.revision-recorded.v1",
      activityId: "01890f47-eae3-7cc0-98c4-dc0c0c073996",
      activityType: "decision.write",
      activityStatus: "succeeded",
      configurationId: "core.aggregate-write",
      configurationVersion: "1.0.0",
      configurationHash: `sha256:${"4".repeat(64)}`,
      agentId: "01890f47-eae3-7cc0-98c4-dc0c0c073997",
      agentType: "human",
      agentRole: "canonical.writer",
      occurredAt: "2026-08-29T16:00:00Z",
    },
  ],
  missingRevisionIds: ["01890f47-eae3-7cc0-98c4-dc0c0c07398f"],
  nextCursor: 4,
  truncated: false,
  truncationReason: null,
  integrityState: "integrity-review",
  legacyEventCount: 1,
  exportAllowed: false,
  exportDenialReason: "integrity-review",
};

const acceptedIntent: IntentDraftProjection = {
  schemaVersion: "1.0",
  intentId: "01890f47-eae3-7cc0-98c4-dc0c0c0739a1",
  revisionId: "01890f47-eae3-7cc0-98c4-dc0c0c0739a2",
  revision: 3,
  revisionContentHash: `sha256:${"a".repeat(64)}`,
  createdAt: "2026-08-29T19:00:00.000Z",
  status: "accepted",
  primaryUseCase: "theory-synthesis",
  epistemicMode: "theory",
  researchObjective: "Explain the bounded mechanism.",
  phenomenon: "observed mechanism",
  unitOfAnalysis: "study",
  levelOfAnalysis: "study",
  contributionIntent: "bounded synthesis",
  sourceKinds: ["peer-reviewed-article"],
  evidenceTypes: ["empirical-study"],
  languageCodes: ["en"],
  startYear: 2000,
  endYear: 2026,
  includePrivateReports: false,
  stoppingConditions: ["researcher-decision"],
  autonomyLevel: "prepare-reversible",
  noveltyStandard: "bounded-comparative",
  noveltyRationale: "Compare only within the accepted corpus.",
  revisionRationale: "Accepted scope.",
  decisionComplete: true,
  unresolvedDecisions: [],
  canRequestAcceptance: false,
  launchReady: true,
};

const recalculationPreview: RecalculationPreview = {
  schemaVersion: "1.0",
  projectId: project.projectId,
  targetRevisionId: lineage.revisionId,
  changeIds: ["01890f47-eae3-7cc0-98c4-dc0c0c0739a3"],
  causes: [
    {
      causeId: "01890f47-eae3-7cc0-98c4-dc0c0c0739a4",
      changeId: "01890f47-eae3-7cc0-98c4-dc0c0c0739a3",
      confidence: "confirmed",
      depth: 1,
      disposition: "stale",
      pathRevisionIds: [lineage.revisionId],
      reason: "A verified evidence dependency changed.",
      reviewRequired: false,
    },
    {
      causeId: "01890f47-eae3-7cc0-98c4-dc0c0c0739a5",
      changeId: "01890f47-eae3-7cc0-98c4-dc0c0c0739a3",
      confidence: "conditional",
      depth: 2,
      disposition: "stale",
      pathRevisionIds: [lineage.revisionId],
      reason: "A researcher-adjudicated claim depends on the evidence.",
      reviewRequired: true,
    },
    {
      causeId: "01890f47-eae3-7cc0-98c4-dc0c0c0739a6",
      changeId: "01890f47-eae3-7cc0-98c4-dc0c0c0739a3",
      confidence: "unknown",
      depth: 3,
      disposition: "unknown-impact",
      pathRevisionIds: [lineage.revisionId],
      reason: "The downstream impact cannot be proven safely.",
      reviewRequired: true,
    },
  ],
  reusableRevisionIds: ["01890f47-eae3-7cc0-98c4-dc0c0c0739a7"],
  replacementRevisionIds: ["01890f47-eae3-7cc0-98c4-dc0c0c0739a8"],
  planSha256: `sha256:${"b".repeat(64)}`,
  policySha256: `sha256:${"c".repeat(64)}`,
  deferPreservesStaleVisibility: true,
};

describe("audit and lineage workspace", () => {
  it("classifies controlled recalculation impacts without hiding uncertain or reusable work", () => {
    expect(recalculationImpactClass(recalculationPreview.causes[0]!)).toBe("automatic");
    expect(recalculationImpactClass(recalculationPreview.causes[1]!)).toBe("review-required");
    expect(recalculationImpactClass(recalculationPreview.causes[2]!)).toBe("blocked");
    expect(acceptedRecalculationIntent({
      schemaVersion: "1.0",
      projectId: project.projectId,
      current: acceptedIntent,
      history: [],
    })).toBe(acceptedIntent);
    expect(acceptedRecalculationIntent({
      schemaVersion: "1.0",
      projectId: project.projectId,
      current: { ...acceptedIntent, status: "draft" },
      history: [],
    })).toBeNull();
  });

  it("drives the generated client through the complete bounded recalculation and restoration path", async () => {
    const requests: CoreApiRequest[] = [];
    const client = createCoreApiClient(async (request) => {
      requests.push(request);
      const body = request.body ? JSON.parse(request.body) as Record<string, unknown> : {};
      const response = request.path === "/projects/intent"
        ? {
            schemaVersion: "1.0",
            projectId: project.projectId,
            current: acceptedIntent,
            history: [{
              revision: acceptedIntent.revision,
              revisionId: acceptedIntent.revisionId,
              revisionContentHash: acceptedIntent.revisionContentHash,
              createdAt: acceptedIntent.createdAt,
              status: acceptedIntent.status,
              primaryUseCase: acceptedIntent.primaryUseCase,
              unresolvedDecisionCount: 0,
            }],
          }
        : request.path === "/projects/recalculation/preview"
          ? recalculationPreview
          : request.path === "/projects/recalculation/schedules"
            ? {
                schemaVersion: "1.0",
                projectId: project.projectId,
                targetRevisionId: body.targetRevisionId,
                planSha256: body.expectedPlanSha256,
                workflowRunId: "01890f47-eae3-7cc0-98c4-dc0c0c0739a9",
                jobId: "01890f47-eae3-7cc0-98c4-dc0c0c0739aa",
                state: "runnable",
              }
            : request.path === "/projects/recalculation/comparisons"
              ? {
                  schemaVersion: "1.0",
                  aggregateId: "01890f47-eae3-7cc0-98c4-dc0c0c0739ab",
                  beforeRevisionId: body.beforeRevisionId,
                  beforeRevision: 4,
                  afterRevisionId: body.afterRevisionId,
                  afterRevision: 5,
                  changedFields: ["knowledgeStatus", "summary"],
                }
              : request.path === "/projects/recalculation/restore-reviews"
                ? {
                    schemaVersion: "1.0",
                    workflowRunId: "01890f47-eae3-7cc0-98c4-dc0c0c0739ac",
                    humanTaskId: "01890f47-eae3-7cc0-98c4-dc0c0c0739ad",
                    snapshotRevision: 1,
                    historySequence: 2,
                    policySha256: recalculationPreview.policySha256,
                  }
                : {
                    schemaVersion: "1.0",
                    projectId: project.projectId,
                    aggregateId: "01890f47-eae3-7cc0-98c4-dc0c0c0739ab",
                    revisionId: "01890f47-eae3-7cc0-98c4-dc0c0c0739ae",
                    revision: 6,
                    knowledgeStatus: "adjudicated",
                    rightsStatus: "allowed",
                  };
      return {
        status: 200,
        contentType: "application/json",
        traceId: "0123456789abcdef0123456789abcdef",
        etag: null,
        body: JSON.stringify(response),
      };
    });
    let clockTick = 0;
    const coordinator = new ControlledRecalculationCoordinator(
      client,
      () => "d".repeat(32),
      () => `2026-09-03T11:00:0${clockTick++}.000Z`,
    );
    const intent = await coordinator.loadAcceptedIntent(project);
    expect(intent).toEqual(acceptedIntent);
    const preview = await coordinator.preview(project, lineage.revisionId);
    const scheduled = await coordinator.schedule(project, preview, intent!, preview.changeIds[0]!);
    const scheduledReplay = await coordinator.schedule(project, preview, intent!, preview.changeIds[0]!);
    const comparison = await coordinator.compare(
      project,
      lineage.revisionId,
      preview.replacementRevisionIds[0]!,
    );
    const review = await coordinator.requestRestoreReview(
      project,
      intent!,
      comparison.beforeRevisionId,
      comparison.afterRevisionId,
    );
    const reviewReplay = await coordinator.requestRestoreReview(
      project,
      intent!,
      comparison.beforeRevisionId,
      comparison.afterRevisionId,
    );
    const restored = await coordinator.restore(
      project,
      review,
      comparison.beforeRevisionId,
      comparison.afterRevisionId,
      "01890f47-eae3-7cc0-98c4-dc0c0c0739af",
    );
    const restoredReplay = await coordinator.restore(
      project,
      review,
      comparison.beforeRevisionId,
      comparison.afterRevisionId,
      "01890f47-eae3-7cc0-98c4-dc0c0c0739af",
    );

    expect(scheduled.planSha256).toBe(preview.planSha256);
    expect(scheduledReplay).toEqual(scheduled);
    expect(reviewReplay).toEqual(review);
    expect(restoredReplay).toEqual(restored);
    expect(restored.revisionId).not.toBe(comparison.beforeRevisionId);
    expect(requests.map((request) => request.path)).toEqual([
      "/projects/intent",
      "/projects/recalculation/preview",
      "/projects/recalculation/schedules",
      "/projects/recalculation/schedules",
      "/projects/recalculation/comparisons",
      "/projects/recalculation/restore-reviews",
      "/projects/recalculation/restore-reviews",
      "/projects/recalculation/restorations",
      "/projects/recalculation/restorations",
    ]);
    expect(requests[2]).toMatchObject({ idempotencyKey: "d".repeat(32) });
    expect(requests[3]).toMatchObject({ idempotencyKey: "d".repeat(32) });
    expect(requests[5]).toMatchObject({ idempotencyKey: "d".repeat(32) });
    expect(requests[6]).toMatchObject({ idempotencyKey: "d".repeat(32) });
    expect(requests[3]!.body).toBe(requests[2]!.body);
    expect(requests[6]!.body).toBe(requests[5]!.body);
    expect(requests[8]!.body).toBe(requests[7]!.body);
    expect(JSON.parse(requests[2]!.body!)).toMatchObject({
      root: project.root,
      targetRevisionId: lineage.revisionId,
      expectedPlanSha256: preview.planSha256,
      intentId: acceptedIntent.intentId,
      intentRevisionId: acceptedIntent.revisionId,
      intentSha256: acceptedIntent.revisionContentHash,
    });
    expect(JSON.parse(requests[7]!.body!)).toMatchObject({
      decisionId: "01890f47-eae3-7cc0-98c4-dc0c0c0739af",
      priorAdjudicatedRevisionId: comparison.beforeRevisionId,
      expectedCurrentRevisionId: comparison.afterRevisionId,
      workflowRunId: review.workflowRunId,
      humanTaskId: review.humanTaskId,
    });
    await expect(coordinator.schedule(
      { ...project, accessMode: "read-only" },
      preview,
      intent!,
      preview.changeIds[0]!,
    )).rejects.toThrow("RO-CORE-MUTATION-UNAVAILABLE");
  });
  it("keeps read-only inspection available while failing closed for unavailable projects", () => {
    expect(lineageAvailability(null)).toEqual({ available: false, reason: "Open a local project to trace lineage." });
    expect(lineageAvailability({ ...project, accessMode: "read-only" })).toEqual({ available: true, reason: null });
    expect(lineageAvailability({ ...project, open: false, accessMode: "closed" })).toEqual({
      available: false,
      reason: "Open this project before tracing lineage.",
    });
  });

  it("builds one bounded exact-revision request after workspace navigation", () => {
    const accepted = provenanceLineageRequest(project, lineage.revisionId, "ancestors", 0);
    expect(accepted).toEqual({
      root: project.root,
      revisionId: lineage.revisionId,
      direction: "ancestors",
      cursor: 0,
      pageSize: 50,
      maxDepth: 8,
    });
    expect(() => provenanceLineageRequest(project, "not-a-revision", "ancestors", 0)).toThrow(
      "RO-CORE-REQUEST-INVALID",
    );
    expect(continuationLineageRequest(accepted, 50)).toEqual({ ...accepted, cursor: 50 });
    expect(continuationLineageRequest(accepted, 50).revisionId).toBe(lineage.revisionId);
    expect(() => continuationLineageRequest({ ...accepted, cursor: 1 }, 50)).toThrow("RO-CORE-REQUEST-INVALID");
  });

  it("uses the generated client for one exact renderer submission and freezes later-page authority", async () => {
    const requests: CoreApiRequest[] = [];
    const client = createCoreApiClient(async (request) => {
      requests.push(request);
      return {
        status: 200,
        contentType: "application/json",
        traceId: "0123456789abcdef0123456789abcdef",
        etag: null,
        body: JSON.stringify(lineage),
      };
    });
    const initial = await loadLineagePage(client, project, lineage.revisionId, "ancestors", 0);
    expect(initial.page).toEqual(lineage);
    expect(requests[0]).toMatchObject({
      path: "/projects/provenance/lineage",
      body: JSON.stringify(initial.request),
    });
    const frozen = continuationLineageRequest(initial.request, 4);
    expect(frozen.revisionId).toBe(lineage.revisionId);
    expect(frozen.direction).toBe("ancestors");
    await expect(loadLineagePage(client, project, lineage.revisionId, "descendants", 0, initial.request))
      .rejects.toThrow("RO-CORE-REQUEST-INVALID");
  });

  it("terminates an empty continuation through the generated client and removes the renderer action", async () => {
    const accepted = provenanceLineageRequest(project, lineage.revisionId, lineage.direction, 0);
    const current = {
      ...lineage,
      items: [lineage.items[0]!],
      missingRevisionIds: [],
      legacyEventCount: 0,
      nextCursor: 1,
      integrityState: "verified" as const,
      exportAllowed: true,
      exportDenialReason: null,
    };
    const requests: CoreApiRequest[] = [];
    const client = createCoreApiClient(async (request) => {
      requests.push(request);
      return {
        status: 200,
        contentType: "application/json",
        traceId: "0123456789abcdef0123456789abcdef",
        etag: null,
        body: JSON.stringify({ ...current, items: [], nextCursor: null }),
      };
    });
    const terminalPage = await loadLineagePage(
      client,
      project,
      lineage.revisionId,
      lineage.direction,
      1,
      accepted,
    );
    const terminalTrace = mergeLineagePage(current, terminalPage.page, 1);
    expect(requests).toHaveLength(1);
    expect(terminalTrace.nextCursor).toBeNull();
    expect(renderToStaticMarkup(
      <AuditLineageWorkspace project={project} announce={() => undefined} initialTrace={terminalTrace} />,
    )).not.toContain("Load more lineage");
  });

  it("keeps selected, superseded, and alternate source records visible with integrity context", () => {
    const root = lineage.items[0]!;
    expect(lineageNodeRole(root, root, "ancestors")).toBe("Selected output");
    expect(lineageNodeRole(lineage.items[1]!, root, "ancestors")).toBe("Invalidation or stale fact");
    expect(lineageNodeRole(lineage.items[2]!, root, "ancestors")).toBe("Upstream source or alternate");
    expect(lineageNodeRole(lineage.items[1]!, root, "descendants")).toBe("Invalidation or stale fact");
    expect(lineageNodeRole(lineage.items[2]!, root, "descendants")).toBe("Downstream output");

    const html = renderToStaticMarkup(
      <AuditLineageWorkspace
        project={project}
        announce={() => undefined}
        initialRevisionId={lineage.revisionId}
        initialTrace={lineage}
      />,
    );

    expect(html).toContain('data-audit-lineage-workspace="true"');
    expect(html).toContain("Exact output revision ID");
    expect(html).toContain("Trace lineage");
    expect(html).toContain("Selected output");
    expect(html).toContain("Invalidation or stale fact");
    expect(html).toContain("Upstream source or alternate");
    expect(html).toContain("wasDerivedFrom ancestors traversal");
    expect(html).toContain("Stale or invalidated");
    expect(html).toContain("Integrity review required");
    expect(html).toContain(lineage.missingRevisionIds[0]);
    expect(html).toContain("1 legacy event");
    expect(html).toContain("not hidden model rationale or chain-of-thought");
    expect(html).toContain("model.synthesis-prompt");
    expect(html).toContain("3.2.0");
    expect(html).toContain("Audit events");
    expect(html).toContain("Rights &amp; egress decisions");
    expect(html).toContain("Human decisions");
    expect(html).toContain("canonical.writer");
    expect(html).toContain("org.research-observatory.decision.revision-recorded.v1");
    expect(html).not.toContain("No human decision is recorded in this trace.");
    expect(html).toContain("Exportable manifest");
    for (const node of lineage.items) {
      expect(html).toContain(node.revisionId);
      expect(html).toContain(node.eventId);
      expect(html).toContain(node.activityId);
    }
  });

  it("exports only a policy-approved content-minimized manifest and rejects incoherent page merges", () => {
    const acceptedQuery = provenanceLineageRequest(project, lineage.revisionId, lineage.direction, 0);
    const exportable = {
      ...lineage,
      missingRevisionIds: [],
      legacyEventCount: 0,
      nextCursor: null,
      integrityState: "verified" as const,
      exportAllowed: true,
      exportDenialReason: null,
    };
    const manifest = exportLineageManifest(exportable, acceptedQuery);
    expect(manifest).toContain('"manifestType": "content-minimized-lineage"');
    expect(manifest).toContain('"completeness": "complete"');
    expect(manifest).toContain('"maxDepth": 8');
    expect(manifest).toContain('"redaction": "research-content-and-raw-prompts-omitted"');
    expect(lineageManifestReady(exportable, acceptedQuery)).toBe(true);
    expect(() => exportLineageManifest({ ...exportable, nextCursor: 4 }, acceptedQuery))
      .toThrow("RO-CORE-EXPORT-DENIED");
    expect(() => exportLineageManifest(lineage, acceptedQuery)).toThrow("RO-CORE-EXPORT-DENIED");
    expect(() => exportLineageManifest(exportable, { ...acceptedQuery, direction: "descendants" }))
      .toThrow("RO-CORE-EXPORT-DENIED");
    expect(lineageManifestReady({
      ...exportable,
      missingRevisionIds: ["01890f47-eae3-7cc0-98c4-dc0c0c0739aa"],
    }, acceptedQuery)).toBe(false);
    expect(lineageManifestReady({ ...exportable, legacyEventCount: 1 }, acceptedQuery)).toBe(false);
    expect(lineageManifestReady({
      ...exportable,
      truncated: true,
      truncationReason: "cursor-limit",
      integrityState: "integrity-review",
      exportAllowed: false,
      exportDenialReason: "integrity-review",
    }, acceptedQuery)).toBe(false);
    expect(() => mergeLineagePage(
      { ...exportable, nextCursor: 3 },
      { ...exportable, items: [exportable.items[0]!], nextCursor: null },
      3,
    )).toThrow("RO-CORE-RESPONSE-INVALID");
    expect(() => mergeLineagePage(
      { ...exportable, items: [{ ...exportable.items[0]!, depth: 2 }], nextCursor: 1 },
      { ...exportable, items: [{ ...exportable.items[1]!, depth: 1 }], nextCursor: null },
      1,
    )).toThrow("RO-CORE-RESPONSE-INVALID");

    const integrityReview = { ...lineage, nextCursor: 4 };
    const verifiedFinal = {
      ...exportable,
      items: [{
        ...exportable.items[1]!,
        factId: "01890f47-eae3-7cc0-98c4-dc0c0c0739a0",
      }],
    };
    const integrityMerged = mergeLineagePage(integrityReview, verifiedFinal, 4);
    expect(integrityMerged).toMatchObject({
      nextCursor: null,
      integrityState: "integrity-review",
      exportAllowed: false,
      exportDenialReason: "integrity-review",
    });
    expect(() => exportLineageManifest(integrityMerged, acceptedQuery)).toThrow("RO-CORE-EXPORT-DENIED");

    const rightsDenied = {
      ...exportable,
      items: [exportable.items[0]!],
      nextCursor: 1,
      exportAllowed: false,
      exportDenialReason: "rights-restricted" as const,
    };
    const rightsMerged = mergeLineagePage(rightsDenied, verifiedFinal, 1);
    expect(rightsMerged).toMatchObject({ exportAllowed: false, exportDenialReason: "rights-restricted" });
    expect(() => exportLineageManifest(rightsMerged, acceptedQuery)).toThrow("RO-CORE-EXPORT-DENIED");

    const missingMerged = mergeLineagePage(
      { ...exportable, items: [exportable.items[0]!], nextCursor: 1 },
      {
        ...verifiedFinal,
        missingRevisionIds: ["01890f47-eae3-7cc0-98c4-dc0c0c0739aa"],
      },
      1,
    );
    expect(missingMerged).toMatchObject({
      integrityState: "integrity-review",
      exportAllowed: false,
      exportDenialReason: "integrity-review",
    });
    expect(() => exportLineageManifest(missingMerged, acceptedQuery)).toThrow("RO-CORE-EXPORT-DENIED");

    const legacyMerged = mergeLineagePage(
      { ...exportable, items: [exportable.items[0]!], nextCursor: 1 },
      { ...verifiedFinal, legacyEventCount: 1 },
      1,
    );
    expect(legacyMerged).toMatchObject({
      legacyEventCount: 1,
      integrityState: "integrity-review",
      exportAllowed: false,
      exportDenialReason: "integrity-review",
    });
    expect(() => exportLineageManifest(legacyMerged, acceptedQuery)).toThrow("RO-CORE-EXPORT-DENIED");

    const truncatedMerged = mergeLineagePage(
      { ...exportable, items: [exportable.items[0]!], nextCursor: 1 },
      {
        ...verifiedFinal,
        truncated: true,
        truncationReason: "scan-limit",
        integrityState: "integrity-review",
        exportAllowed: false,
        exportDenialReason: "integrity-review",
      },
      1,
    );
    expect(truncatedMerged).toMatchObject({
      truncated: true,
      truncationReason: "scan-limit",
      integrityState: "integrity-review",
      exportAllowed: false,
      exportDenialReason: "integrity-review",
    });
    expect(() => exportLineageManifest(truncatedMerged, acceptedQuery)).toThrow("RO-CORE-EXPORT-DENIED");
    const truncatedHtml = renderToStaticMarkup(
      <AuditLineageWorkspace project={project} announce={() => undefined} initialTrace={truncatedMerged} />,
    );
    expect(truncatedHtml).toContain("Lineage trace is incomplete");
    expect(truncatedHtml).toContain("scan limit");
    expect(truncatedHtml).toContain("Export denied: integrity review is required");

    const terminal = mergeLineagePage(
      { ...exportable, items: [exportable.items[0]!], nextCursor: 1 },
      { ...exportable, items: [], nextCursor: null },
      1,
    );
    expect(terminal.nextCursor).toBeNull();
    expect(renderToStaticMarkup(
      <AuditLineageWorkspace project={project} announce={() => undefined} initialTrace={terminal} />,
    )).not.toContain("Load more lineage");
    expect(() => mergeLineagePage(
      { ...exportable, items: [exportable.items[0]!], nextCursor: 1 },
      { ...exportable, items: [], nextCursor: 1 },
      1,
    )).toThrow("RO-CORE-RESPONSE-INVALID");
  });

  it("renders a recovery-oriented empty state without offering a trace against no project", () => {
    const html = renderToStaticMarkup(<AuditLineageWorkspace project={null} announce={() => undefined} />);
    expect(html).toContain("Open a local project to trace lineage.");
    expect(html).not.toContain('data-trace-lineage="true"');
  });

  it("maps every task-owned approved page region to an executable implementation selector", () => {
    const contract = JSON.parse(readFileSync(
      new URL("./audit-lineage.conformance.json", import.meta.url),
      "utf8",
    )) as {
      referenceId: string;
      regions: Record<string, string>;
      interactions: Record<string, string>;
      states: string[];
    };
    expect(contract.referenceId).toBe("RO-UI-ACADEMIC-MINIMAL-1.5");
    expect(Object.keys(contract.regions)).toEqual([
      "source-to-output-lineage",
      "model-schema-prompt-versions",
      "rights-and-egress-decisions",
      "human-decisions",
      "audit-events",
      "exportable-manifest",
      "stale-status",
      "recalculation-impact-preview",
      "current-policy-status",
      "immutable-revision-comparison",
      "human-gated-restoration",
    ]);
    expect(contract.states).toContain("rights-restricted-export-denial");
    const html = renderToStaticMarkup(
      <AuditLineageWorkspace
        project={project}
        announce={() => undefined}
        initialRevisionId={lineage.revisionId}
        initialTrace={lineage}
      />,
    );
    const selectorMarkers = [...Object.values(contract.regions), ...Object.values(contract.interactions)]
      .flatMap((selector) => [...selector.matchAll(/\[([^\]]+)\]|\.([a-z0-9-]+)/g)])
      .map((match) => match[1] ?? match[2]);
    for (const marker of selectorMarkers) {
      expect(html, `implementation marker for ${marker}`).toContain(marker);
    }
  });
});
