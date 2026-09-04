import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  CORE_API_OPENAPI_SHA256,
  CoreApiClientError,
  createCoreApiClient,
  decodeCacheClearPreview,
  decodeCacheClearResult,
  decodeIntentDraftProjection,
  decodeIntentGoverningReference,
  decodeIntentImpactPreview,
  decodeIntentPolicyDecision,
  decodeIntentWorkspaceProjection,
  decodePrivacyPolicyProjection,
  decodeProblemDetail,
  decodeProjectProjection,
  decodeProvenanceLineagePage,
  decodeRecalculationComparison,
  decodeRecalculationPreview,
  decodeRecalculationRestoredRevision,
  decodeRecalculationRestoreReview,
  decodeRecalculationSchedule,
  decodeVersionResponse,
  decodeWorkflowTaskCenterPage,
  decodeWorkflowTaskCenterRun,
  decodeWorkflowProfileCatalogProjection,
  decodeWorkflowProgressProjection,
  evaluateCoreApiCompatibility,
  parseOperationEventStream,
  type CoreApiResponse,
  type ProvenanceLineagePage,
  type RecalculationComparisonProjection,
  type RecalculationPreview,
  type RecalculationRestoredRevision,
  type RecalculationRestoreReviewProjection,
  type RecalculationScheduleProjection,
  type VersionResponse,
  type WorkflowTaskCenterRun,
  type WorkflowProgressProjection,
  workflowEtag,
} from "./generated";

const traceId = "0123456789abcdef0123456789abcdef";
const compatible: VersionResponse = {
  schemaVersion: "1.0",
  service: "research-observatory-core",
  version: "0.1.0",
  apiVersion: "1.0.0",
  minimumClientApiVersion: "1.0.0",
  maximumClientApiVersionExclusive: "2.0.0",
};

function response(status: number, body: unknown, contentType = "application/json", etag: string | null = null): CoreApiResponse {
  return { status, contentType, traceId, etag, body: JSON.stringify(body) };
}

describe("generated Core API client", () => {
  it("binds generated source to the exact OpenAPI bytes", () => {
    const path = fileURLToPath(new URL("./openapi.json", import.meta.url));
    expect(createHash("sha256").update(readFileSync(path)).digest("hex")).toBe(CORE_API_OPENAPI_SHA256);
  });

  it("provides a strict end-to-end recalculation client surface", async () => {
    const projectId = "01890f47-eae3-4cc0-98c4-dc0c0c073981";
    const targetRevisionId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d041";
    const priorRevisionId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d042";
    const changeId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d043";
    const intentId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d044";
    const intentRevisionId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d045";
    const workflowRunId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d046";
    const humanTaskId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d047";
    const decisionId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d048";
    const restoredRevisionId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d049";
    const aggregateId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d04a";
    const jobId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d04b";
    const causeId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d04c";
    const planSha256 = `sha256:${"a".repeat(64)}`;
    const policySha256 = `sha256:${"b".repeat(64)}`;
    const requestedAt = "2026-09-02T12:00:00.000Z";
    const preview: RecalculationPreview = {
      schemaVersion: "1.0",
      projectId,
      targetRevisionId,
      planSha256,
      policySha256,
      changeIds: [changeId],
      replacementRevisionIds: [],
      reusableRevisionIds: [priorRevisionId],
      causes: [{
        causeId,
        changeId,
        disposition: "stale",
        reason: "A material source revision changed.",
        depth: 1,
        confidence: "confirmed",
        reviewRequired: true,
        pathRevisionIds: [priorRevisionId, targetRevisionId],
      }],
      deferPreservesStaleVisibility: true,
    };
    const scheduled: RecalculationScheduleProjection = {
      schemaVersion: "1.0",
      projectId,
      targetRevisionId,
      planSha256,
      workflowRunId,
      jobId,
      state: "runnable",
    };
    const comparison: RecalculationComparisonProjection = {
      schemaVersion: "1.0",
      aggregateId,
      beforeRevisionId: priorRevisionId,
      afterRevisionId: targetRevisionId,
      beforeRevision: 1,
      afterRevision: 2,
      changedFields: ["knowledgeStatus"],
    };
    const restoreReview: RecalculationRestoreReviewProjection = {
      schemaVersion: "1.0",
      workflowRunId,
      humanTaskId,
      snapshotRevision: 1,
      historySequence: 7,
      policySha256,
    };
    const restored: RecalculationRestoredRevision = {
      schemaVersion: "1.0",
      projectId,
      aggregateId,
      revisionId: restoredRevisionId,
      revision: 3,
      knowledgeStatus: "adjudicated",
      rightsStatus: "allowed",
    };
    const requests: unknown[] = [];
    const client = createCoreApiClient(async (request) => {
      requests.push(request);
      const bodies: Record<string, unknown> = {
        "/projects/recalculation/preview": preview,
        "/projects/recalculation/schedules": scheduled,
        "/projects/recalculation/comparisons": comparison,
        "/projects/recalculation/restore-reviews": restoreReview,
        "/projects/recalculation/restorations": restored,
      };
      return response(200, bodies[request.path]);
    });
    await expect(client.previewRecalculation({ root: "C:/Research/study-one", targetRevisionId }))
      .resolves.toEqual(preview);
    await expect(client.scheduleRecalculation({
      root: "C:/Research/study-one",
      targetRevisionId,
      changeId,
      expectedPlanSha256: planSha256,
      intentId,
      intentRevisionId,
      intentSha256: policySha256,
      requestedAt,
    }, "c".repeat(32))).resolves.toEqual(scheduled);
    await expect(client.compareRecalculation({
      root: "C:/Research/study-one",
      beforeRevisionId: priorRevisionId,
      afterRevisionId: targetRevisionId,
    })).resolves.toEqual(comparison);
    await expect(client.requestRecalculationRestoreReview({
      root: "C:/Research/study-one",
      beforeRevisionId: priorRevisionId,
      afterRevisionId: targetRevisionId,
      intentId,
      intentRevisionId,
      intentSha256: policySha256,
      requestedAt,
    }, "d".repeat(32))).resolves.toEqual(restoreReview);
    await expect(client.restoreRecalculationRevision({
      root: "C:/Research/study-one",
      priorAdjudicatedRevisionId: priorRevisionId,
      expectedCurrentRevisionId: targetRevisionId,
      workflowRunId,
      humanTaskId,
      decisionId,
      modifiedAt: requestedAt,
    })).resolves.toEqual(restored);

    expect(requests).toHaveLength(5);
    expect(requests[1]).toMatchObject({
      path: "/projects/recalculation/schedules",
      ifMatch: null,
      idempotencyKey: "c".repeat(32),
    });
    expect(JSON.parse((requests[1] as { body: string }).body)).toEqual({
      root: "C:/Research/study-one",
      targetRevisionId,
      changeId,
      expectedPlanSha256: planSha256,
      intentId,
      intentRevisionId,
      intentSha256: policySha256,
      requestedAt,
    });
    expect(decodeRecalculationPreview({ ...preview, actorId: "spoofed" })).toBeNull();
    expect(decodeRecalculationSchedule({ ...scheduled, planSha256: "sha256:not-canonical" })).toBeNull();
    expect(decodeRecalculationComparison({ ...comparison, afterRevision: 1 })).toBeNull();
    expect(decodeRecalculationRestoreReview({ ...restoreReview, policySha256: null })).toBeNull();
    expect(decodeRecalculationRestoredRevision({ ...restored, rightsStatus: "unverified" })).toBeNull();
  });

  it("decodes bounded lineage exactly and posts the governed lineage request", async () => {
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
      ],
      missingRevisionIds: ["01890f47-eae3-7cc0-98c4-dc0c0c07398f"],
      nextCursor: null,
      truncated: false,
      truncationReason: null,
      integrityState: "integrity-review",
      legacyEventCount: 1,
      exportAllowed: false,
      exportDenialReason: "integrity-review",
    };

    expect(decodeProvenanceLineagePage(lineage)).toEqual(lineage);
    expect(decodeProvenanceLineagePage({ ...lineage, ungoverned: true })).toBeNull();
    expect(decodeProvenanceLineagePage({
      ...lineage,
      items: [{ ...lineage.items[0], revisionId: "not-a-uuid" }],
    })).toBeNull();
    expect(decodeProvenanceLineagePage({
      ...lineage,
      items: [{ ...lineage.items[0], configurationHash: "sha256:not-canonical" }],
    })).toBeNull();

    const requests: unknown[] = [];
    const client = createCoreApiClient(async (request) => {
      requests.push(request);
      return response(200, lineage);
    });
    await expect(client.lineage({
      root: "C:/Research/study-one",
      revisionId: lineage.revisionId,
      direction: "ancestors",
      cursor: 0,
      pageSize: 50,
      maxDepth: 8,
    })).resolves.toEqual(lineage);
    expect(requests).toEqual([{
      method: "POST",
      path: "/projects/provenance/lineage",
      body: JSON.stringify({
        root: "C:/Research/study-one",
        revisionId: lineage.revisionId,
        direction: "ancestors",
        cursor: 0,
        pageSize: 50,
        maxDepth: 8,
      }),
      ifMatch: null,
      idempotencyKey: null,
    }]);
    await expect(client.lineage({
      root: "C:/Research/study-one",
      revisionId: lineage.revisionId,
      direction: "ancestors",
      cursor: 0,
      pageSize: 101,
      maxDepth: 8,
    })).rejects.toThrow("RO-CORE-REQUEST-INVALID");

    const mismatched = createCoreApiClient(async () => response(200, {
      ...lineage,
      revisionId: "01890f47-eae3-7cc0-98c4-dc0c0c073980",
    }));
    await expect(mismatched.lineage({
      root: "C:/Research/study-one",
      revisionId: lineage.revisionId,
      direction: "ancestors",
      cursor: 0,
      pageSize: 50,
      maxDepth: 8,
    })).rejects.toThrow("RO-CORE-RESPONSE-INVALID");

    const unavailable = {
      ...lineage,
      items: [],
      missingRevisionIds: [lineage.revisionId],
      nextCursor: null,
      integrityState: "integrity-review" as const,
      exportAllowed: false,
      exportDenialReason: "integrity-review" as const,
    };
    const missingRoot = createCoreApiClient(async () => response(200, unavailable));
    await expect(missingRoot.lineage({
      root: "C:/Research/study-one",
      revisionId: lineage.revisionId,
      direction: "ancestors",
      cursor: 0,
      pageSize: 50,
      maxDepth: 8,
    })).resolves.toEqual(unavailable);

    const request = {
      root: "C:/Research/study-one",
      revisionId: lineage.revisionId,
      direction: "ancestors" as const,
      cursor: 0,
      pageSize: 50,
      maxDepth: 8,
    };
    for (const invalid of [
      {
        ...lineage,
        items: Array.from({ length: 51 }, (_, index) => ({
          ...lineage.items[0]!,
          factId: `01890f47-eae3-7cc0-98c4-${(index + 1000).toString(16).padStart(12, "0")}`,
        })),
      },
      { ...lineage, items: [{ ...lineage.items[0]!, depth: 9 }] },
      { ...lineage, nextCursor: 0 },
      { ...lineage, items: [lineage.items[0]!, { ...lineage.items[0]! }] },
      { ...lineage, items: lineage.items.filter((item) => item.depth !== 0) },
    ]) {
      const adversarial = createCoreApiClient(async () => response(200, invalid));
      await expect(adversarial.lineage(request)).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
    }

    const continuationRequest = { ...request, cursor: 50 };
    for (const invalidContinuation of [
      {
        ...lineage,
        items: [],
        missingRevisionIds: [],
        nextCursor: 50,
        integrityState: "verified" as const,
        exportAllowed: true,
        exportDenialReason: null,
      },
      {
        ...lineage,
        items: [{ ...lineage.items[1]!, depth: 1 }],
        missingRevisionIds: [],
        nextCursor: 49,
        integrityState: "verified" as const,
        exportAllowed: true,
        exportDenialReason: null,
      },
    ]) {
      const adversarial = createCoreApiClient(async () => response(200, invalidContinuation));
      await expect(adversarial.lineage(continuationRequest)).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
    }

    const terminalContinuation = {
      ...lineage,
      items: [],
      missingRevisionIds: [],
      legacyEventCount: 0,
      nextCursor: null,
      integrityState: "verified" as const,
      exportAllowed: true,
      exportDenialReason: null,
    };
    const terminating = createCoreApiClient(async () => response(200, terminalContinuation));
    await expect(terminating.lineage(continuationRequest)).resolves.toEqual(terminalContinuation);

    for (const contradictory of [
      {
        ...lineage,
        missingRevisionIds: ["01890f47-eae3-7cc0-98c4-dc0c0c0739aa"],
        legacyEventCount: 0,
        nextCursor: null,
        integrityState: "verified" as const,
        exportAllowed: true,
        exportDenialReason: null,
      },
      {
        ...lineage,
        missingRevisionIds: [],
        legacyEventCount: 1,
        nextCursor: null,
        integrityState: "verified" as const,
        exportAllowed: true,
        exportDenialReason: null,
      },
      {
        ...lineage,
        missingRevisionIds: [],
        legacyEventCount: 0,
        truncated: true,
        truncationReason: "cursor-limit" as const,
        nextCursor: null,
        integrityState: "verified" as const,
        exportAllowed: true,
        exportDenialReason: null,
      },
    ]) {
      const firstPageAdversary = createCoreApiClient(async () => response(200, contradictory));
      await expect(firstPageAdversary.lineage(request)).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
      const continuationAdversary = createCoreApiClient(async () => response(200, {
        ...contradictory,
        items: [contradictory.items[1]!],
      }));
      await expect(continuationAdversary.lineage(continuationRequest))
        .rejects.toThrow("RO-CORE-RESPONSE-INVALID");
    }

    const boundedTruncation = {
      ...lineage,
      missingRevisionIds: [],
      legacyEventCount: 0,
      truncated: true,
      truncationReason: "scan-limit" as const,
      nextCursor: null,
      integrityState: "integrity-review" as const,
      exportAllowed: false,
      exportDenialReason: "integrity-review" as const,
    };
    const bounded = createCoreApiClient(async () => response(200, boundedTruncation));
    await expect(bounded.lineage(request)).resolves.toEqual(boundedTruncation);
    expect(decodeProvenanceLineagePage({
      ...boundedTruncation,
      truncated: false,
    })).toBeNull();
  });

  it("decodes and evaluates only the exact compatible version envelope", async () => {
    expect(decodeVersionResponse(compatible)).toEqual(compatible);
    expect(evaluateCoreApiCompatibility(compatible)).toMatchObject({ ok: true, code: "RO-CORE-API-COMPATIBLE" });
    expect(evaluateCoreApiCompatibility({ ...compatible, apiVersion: "2.0.0" })).toMatchObject({
      ok: false,
      code: "RO-CORE-API-INCOMPATIBLE",
    });
    expect(decodeVersionResponse({ ...compatible, extra: "not governed" })).toBeNull();

    const requests: unknown[] = [];
    const client = createCoreApiClient(async (request) => {
      requests.push(request);
      return response(200, compatible);
    });
    await expect(client.version()).resolves.toEqual(compatible);
    expect(requests).toEqual([{
      method: "GET",
      path: "/runtime/version",
      body: null,
      ifMatch: null,
      idempotencyKey: null,
    }]);
  });

  it("preserves safe problem details and trace IDs without surfacing unknown fields", async () => {
    const problem = {
      type: "urn:research-observatory:problem:operation-not-found",
      title: "Operation was not found",
      status: 404,
      detail: "The requested operation is unavailable.",
      code: "RO-CORE-OPERATION-NOT-FOUND",
      traceId,
      retryable: false,
      remediation: "Refresh operation status.",
    };
    expect(decodeProblemDetail(problem)).toEqual(problem);
    const client = createCoreApiClient(async () => response(404, problem, "application/problem+json"));
    await expect(client.operation("op-missing")).rejects.toMatchObject({
      name: "CoreApiClientError",
      problem,
    } satisfies Partial<CoreApiClientError>);
    expect(decodeProblemDetail({ ...problem, privatePath: "C:/research/private" })).toBeNull();
    const wrongProblemMedia = createCoreApiClient(async () => response(404, problem, "text/html"));
    await expect(wrongProblemMedia.operation("op-missing")).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
    await expect(wrongProblemMedia.events("op-missing")).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
  });

  it("parses monotonic SSE frames and rejects forged or reordered events", () => {
    const event = {
      schemaVersion: "1.0",
      operationId: "op-first",
      sequence: 1,
      state: "running",
      progressPercent: 25,
      terminal: false,
      traceId,
    };
    const frame = `id: 1\nevent: operation-progress\ndata: ${JSON.stringify(event)}\n\n`;
    expect(parseOperationEventStream(frame)).toEqual([event]);
    expect(() => parseOperationEventStream(frame + frame)).toThrow("RO-CORE-RESPONSE-INVALID");
    expect(() => parseOperationEventStream(`data: ${JSON.stringify({ ...event, secret: "hidden" })}\n\n`)).toThrow(
      "RO-CORE-RESPONSE-INVALID",
    );
  });

  it("bounds pagination, operation identities, and untrusted transport responses", async () => {
    const client = createCoreApiClient(async () => response(200, { schemaVersion: "1.0", items: [], nextCursor: null }));
    await expect(client.operations(null, 0)).rejects.toThrow("RO-CORE-REQUEST-INVALID");
    await expect(client.operation("https://evil.invalid")).rejects.toThrow("RO-CORE-REQUEST-INVALID");
    const hostile = createCoreApiClient(async () => ({
      status: 200,
      contentType: "application/json",
      traceId,
      etag: null,
      body: "{not-json",
    }));
    await expect(hostile.version()).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
    const redirected = createCoreApiClient(async () => response(302, compatible));
    await expect(redirected.version()).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
  });

  it("carries ETag and idempotency preconditions through cancellation", async () => {
    const operation = {
      schemaVersion: "1.0",
      operationId: "op-first",
      kind: "runtime.fixture",
      state: "running",
      sequence: 1,
      progressPercent: 25,
      cancellationRequested: false,
      createdAt: "2026-08-12T00:00:00Z",
      updatedAt: "2026-08-12T00:00:01Z",
      traceId,
    };
    const requests: unknown[] = [];
    const client = createCoreApiClient(async (request) => {
      requests.push(request);
      return response(200, operation, "application/json", '"op-first-1"');
    });
    await expect(client.operation("op-first")).resolves.toEqual({ operation, etag: '"op-first-1"' });
    await expect(client.cancel("op-first", '"op-first-1"', "a".repeat(32))).resolves.toEqual({
      operation,
      etag: '"op-first-1"',
    });
    expect(requests.at(-1)).toEqual({
      method: "POST",
      path: "/runtime/operations/op-first/cancel",
      body: null,
      ifMatch: '"op-first-1"',
      idempotencyKey: "a".repeat(32),
    });
    await expect(client.cancel("op-first", "not-an-etag", "a".repeat(32))).rejects.toThrow(
      "RO-CORE-REQUEST-INVALID",
    );
    const mismatched = createCoreApiClient(async () => response(200, operation, "application/json", '"op-other-1"'));
    await expect(mismatched.operation("op-first")).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
  });

  it("binds project commands and responses to exact local lifecycle contracts", async () => {
    const projection = {
      schemaVersion: "1.0",
      projectId: "11111111-1111-4111-8111-111111111111",
      displayName: "Study One",
      templateId: "theory-synthesis",
      lifecycleState: "active" as const,
      root: "C:/Research/study-one",
      open: true,
      accessMode: "read-write" as const,
      compatibilityState: "compatible" as const,
      packageFormatVersion: "1.0.0",
      backupRequiredBeforeRepair: false,
      recoveryAction: "none" as const,
      revision: 0,
      deleteConfirmation: "delete:11111111-1111-4111-8111-111111111111",
    };
    expect(decodeProjectProjection(projection)).toEqual(projection);
    expect(decodeProjectProjection({ ...projection, privatePath: "C:/private" })).toBeNull();
    expect(decodeProjectProjection({ ...projection, lifecycleState: "archived", open: true })).toBeNull();
    expect(decodeProjectProjection({ ...projection, compatibilityState: "newer-unsupported" })).toBeNull();
    expect(decodeProjectProjection({
      ...projection,
      deleteConfirmation: "delete:22222222-2222-4222-8222-222222222222",
    })).toBeNull();
    expect(decodeProjectProjection({ ...projection, packageFormatVersion: "9007199254740992.0.0" })).toBeNull();
    expect(decodeProjectProjection({
      ...projection,
      accessMode: "read-only",
      compatibilityState: "newer-unsupported",
      packageFormatVersion: "2.0.0",
      backupRequiredBeforeRepair: true,
      recoveryAction: "backup-then-use-compatible-application",
    })).toEqual({
      ...projection,
      accessMode: "read-only",
      compatibilityState: "newer-unsupported",
      packageFormatVersion: "2.0.0",
      backupRequiredBeforeRepair: true,
      recoveryAction: "backup-then-use-compatible-application",
    });
    expect(decodeProjectProjection({
      ...projection,
      accessMode: "read-only",
      compatibilityState: "newer-unsupported",
      packageFormatVersion: "2.0.0",
      backupRequiredBeforeRepair: true,
      recoveryAction: "backup-then-migrate",
    })).toBeNull();
    expect(decodeProjectProjection({
      ...projection,
      accessMode: "read-only",
      compatibilityState: "migration-required",
      packageFormatVersion: "0.9.0",
      backupRequiredBeforeRepair: true,
      recoveryAction: "backup-then-use-compatible-application",
    })).toBeNull();

    const requests: unknown[] = [];
    const client = createCoreApiClient(async (request) => {
      requests.push(request);
      return response(200, projection);
    });
    await client.createProject({
      parentDirectory: "C:/Research",
      directoryName: "study-one",
      displayName: "Study One",
      primaryUseCase: "theory-synthesis",
      researchObjective: "Explain a bounded phenomenon.",
    });
    await client.archiveProject({ root: projection.root });
    await client.deleteProject({ root: projection.root, confirmation: projection.deleteConfirmation });
    expect(requests.map((request) => (request as { path: string }).path)).toEqual([
      "/projects", "/projects/archive", "/projects/delete",
    ]);
    expect(JSON.parse((requests[0] as { body: string }).body)).toEqual({
      parentDirectory: "C:/Research",
      directoryName: "study-one",
      displayName: "Study One",
      primaryUseCase: "theory-synthesis",
      researchObjective: "Explain a bounded phenomenon.",
    });
    await expect(client.openProject({ root: "relative/project" })).rejects.toThrow("RO-CORE-REQUEST-INVALID");
    await expect(client.deleteProject({ root: projection.root, confirmation: "delete:wrong" })).rejects.toThrow(
      "RO-CORE-REQUEST-INVALID",
    );
  });

  it("strictly decodes and requests the governed workflow profile catalog", async () => {
    const profileIds = [
      "rapid-orientation", "systematic-review", "living-review", "theory-synthesis",
      "hermeneutic-inquiry", "critical-problematization", "technical-landscape", "novelty-audit",
      "empirical-study-design", "empirical-study-to-article", "empirical-results-to-article",
      "theory-article-development", "critical-article-development", "manuscript-review-revision",
    ] as const;
    const guidanceByProfile = {
      "rapid-orientation": {
        example: "Map the main approaches and unresolved questions in a new field.",
        evidenceTypes: ["empirical-study", "systematic-review"],
        noveltyStandard: "not-claimed",
        autonomyLevel: "suggest",
        stoppingConditions: ["coverage-threshold"],
        warning: "Rapid orientation supports bounded understanding; it does not claim exhaustive coverage.",
      },
      "systematic-review": {
        example: "Estimate and explain an intervention effect from eligible studies.",
        evidenceTypes: ["empirical-study", "systematic-review"],
        noveltyStandard: "bounded-comparative",
        autonomyLevel: "suggest",
        stoppingConditions: ["coverage-threshold"],
        warning: "Coverage claims remain bounded by the recorded protocol, sources, dates, and languages.",
      },
      "living-review": {
        example: "Maintain an evidence synthesis as qualifying studies appear.",
        evidenceTypes: ["empirical-study", "systematic-review"],
        noveltyStandard: "incremental",
        autonomyLevel: "suggest",
        stoppingConditions: ["coverage-threshold"],
        warning: "Every update preserves its search boundary and prior synthesis revision.",
      },
      "theory-synthesis": {
        example: "Reconcile competing mechanisms into a bounded conceptual model.",
        evidenceTypes: ["theoretical-work", "empirical-study"],
        noveltyStandard: "theoretical",
        autonomyLevel: "suggest",
        stoppingConditions: ["interpretive-saturation"],
        warning: "Conceptual integration must preserve disagreements and evidentiary limits.",
      },
      "hermeneutic-inquiry": {
        example: "Develop a situated interpretation across a bounded textual corpus.",
        evidenceTypes: ["interpretive-text"],
        noveltyStandard: "interpretive",
        autonomyLevel: "suggest",
        stoppingConditions: ["interpretive-saturation", "researcher-decision"],
        warning: "Interpretations remain researcher-authored and tied to the recorded corpus and frame.",
      },
      "critical-problematization": {
        example: "Surface exclusions and consequences within a dominant framing.",
        evidenceTypes: ["critical-analysis", "stakeholder-account"],
        noveltyStandard: "critical",
        autonomyLevel: "suggest",
        stoppingConditions: ["interpretive-saturation", "researcher-decision"],
        warning: "The workflow must preserve standpoint, counter-evidence, and affected voices.",
      },
      "technical-landscape": {
        example: "Compare architectures and evaluated capabilities for a technical domain.",
        evidenceTypes: ["technical-evaluation", "standard", "dataset"],
        noveltyStandard: "bounded-comparative",
        autonomyLevel: "suggest",
        stoppingConditions: ["benchmark-complete"],
        warning: "Comparisons are limited to compatible evidence, versions, and benchmark conditions.",
      },
      "novelty-audit": {
        example: "Challenge a proposed contribution against the closest documented alternatives.",
        evidenceTypes: ["empirical-study", "theoretical-work", "technical-evaluation"],
        noveltyStandard: "bounded-comparative",
        autonomyLevel: "suggest",
        stoppingConditions: ["nearest-prior-work-challenged"],
        warning: "A novelty claim is provisional until nearest prior work and plausible counterexamples are challenged.",
      },
      "empirical-study-design": {
        example: "Design a study without inventing participants, results, or feasibility evidence.",
        evidenceTypes: ["empirical-study", "systematic-review"],
        noveltyStandard: "methodological",
        autonomyLevel: "suggest",
        stoppingConditions: ["protocol-complete"],
        warning: "The researcher retains authority over ethics, recruitment, conduct, and interpretation.",
      },
      "empirical-study-to-article": {
        example: "Develop a manuscript from a documented study and analysis plan.",
        evidenceTypes: ["empirical-study", "dataset"],
        noveltyStandard: "contextual",
        autonomyLevel: "suggest",
        stoppingConditions: ["protocol-complete", "researcher-decision"],
        warning: "Unreported or missing results remain unreported or missing.",
      },
      "empirical-results-to-article": {
        example: "Develop an article from completed, traceable empirical results.",
        evidenceTypes: ["empirical-study", "dataset"],
        noveltyStandard: "incremental",
        autonomyLevel: "suggest",
        stoppingConditions: ["researcher-decision"],
        warning: "No result, statistic, or participant detail may be inferred when absent.",
      },
      "theory-article-development": {
        example: "Develop a theory article from traceable concepts and propositions.",
        evidenceTypes: ["theoretical-work", "empirical-study"],
        noveltyStandard: "theoretical",
        autonomyLevel: "suggest",
        stoppingConditions: ["interpretive-saturation", "researcher-decision"],
        warning: "The system can prepare arguments; the researcher owns interpretation and claims.",
      },
      "critical-article-development": {
        example: "Develop a critical article with explicit standpoint and counter-evidence.",
        evidenceTypes: ["critical-analysis", "stakeholder-account", "interpretive-text"],
        noveltyStandard: "critical",
        autonomyLevel: "suggest",
        stoppingConditions: ["interpretive-saturation", "researcher-decision"],
        warning: "The article must not erase contested positions or affected perspectives.",
      },
      "manuscript-review-revision": {
        example: "Address reviewer comments without silently broadening claims.",
        evidenceTypes: ["empirical-study", "theoretical-work", "technical-evaluation"],
        noveltyStandard: "not-claimed",
        autonomyLevel: "suggest",
        stoppingConditions: ["researcher-decision"],
        warning: "Reviewer responses and claim changes remain explicit, traceable researcher decisions.",
      },
    } as const;
    const portableCatalogPath = fileURLToPath(new URL(
      "../workflow-profile/fixtures/approved-workflow-profile-catalog.v1.json",
      import.meta.url,
    ));
    const portableCatalog = JSON.parse(readFileSync(portableCatalogPath, "utf8")) as {
      readonly registeredToolPageContractIds: readonly string[];
      readonly profiles: ReadonlyArray<{
        readonly profileId: keyof typeof guidanceByProfile;
        readonly title: string;
        readonly purpose: string;
        readonly expectedOutputs: readonly string[];
        readonly cyclePolicy: "linear" | "revisitable";
        readonly stages: ReadonlyArray<{
          readonly stageKey: string;
          readonly order: number;
          readonly pageContractId: string;
          readonly optional: boolean;
          readonly rationale: string;
          readonly checkpoint: {
            readonly state: "unknown" | "optional-human" | "required-human" | "not-applicable";
            readonly rationale: string;
          };
        }>;
      }>;
    };
    const epistemicModeByProfile = {
      "rapid-orientation": "systematic",
      "systematic-review": "systematic",
      "living-review": "systematic",
      "theory-synthesis": "theory",
      "hermeneutic-inquiry": "hermeneutic",
      "critical-problematization": "critical",
      "technical-landscape": "technical",
      "novelty-audit": "novelty",
      "empirical-study-design": "empirical",
      "empirical-study-to-article": "empirical",
      "empirical-results-to-article": "empirical",
      "theory-article-development": "theory",
      "critical-article-development": "critical",
      "manuscript-review-revision": "empirical",
    } as const;
    const stageLabel = (pageContractId: string): string => pageContractId === "intent-contract.html"
      ? "Research Intent"
      : pageContractId
        .replace(/\.html$/, "")
        .split("-")
        .map((part) => part === "and" ? "&" : `${part.slice(0, 1).toUpperCase()}${part.slice(1)}`)
        .join(" ");
    const catalog = {
      schemaVersion: "1.0",
      referenceId: "RO-UI-ACADEMIC-MINIMAL-1.5",
      referenceVersion: "1.5",
      profileCatalogVersion: "1.0.0",
      profileCatalogHash: "sha256:0a3887774b30bb2d2d7fced5c9e43452e7e34993407a6122155b740814350e49",
      intentGuidanceVersion: "1.0.0",
      intentGuidanceHash: "sha256:2feffbaf216da3adb4d8fe0b3ca6e2579cdc2dcedc2d57341086a14def5fe0d2",
      allToolsAccessible: true,
      evidenceRequirementsUnchanged: true,
      provenanceRequirementsUnchanged: true,
      registeredToolPageContractIds: portableCatalog.registeredToolPageContractIds,
      profiles: portableCatalog.profiles.map((profile) => {
        const profileId = profile.profileId;
        const guidance = guidanceByProfile[profileId];
        return {
          profileId,
          epistemicMode: epistemicModeByProfile[profileId],
          title: profile.title,
          purpose: profile.purpose,
          example: guidance.example,
          expectedOutputs: profile.expectedOutputs,
          processForm: profile.cyclePolicy,
          defaultEvidenceTypes: guidance.evidenceTypes,
          defaultNoveltyStandard: guidance.noveltyStandard,
          defaultAutonomyLevel: guidance.autonomyLevel,
          defaultStoppingConditions: guidance.stoppingConditions,
          warning: guidance.warning,
          stages: profile.stages.map((stage) => ({
            stageKey: stage.stageKey,
            order: stage.order,
            pageContractId: stage.pageContractId,
            label: stageLabel(stage.pageContractId),
            optional: stage.optional,
            rationale: stage.rationale,
            checkpointState: stage.checkpoint.state,
            checkpointRationale: stage.checkpoint.rationale,
          })),
        };
      }),
    };
    expect(decodeWorkflowProfileCatalogProjection(catalog)).toEqual(catalog);
    expect(decodeWorkflowProfileCatalogProjection({
      ...catalog,
      intentGuidanceHash: `sha256:${"f".repeat(64)}`,
    })).toBeNull();
    expect(decodeWorkflowProfileCatalogProjection({ ...catalog, allToolsAccessible: false })).toBeNull();
    expect(decodeWorkflowProfileCatalogProjection({ ...catalog, profiles: catalog.profiles.slice(1) })).toBeNull();
    expect(decodeWorkflowProfileCatalogProjection({
      ...catalog,
      profiles: catalog.profiles.map((profile) => profile.profileId === "systematic-review"
        ? { ...profile, defaultStoppingConditions: ["researcher-decision"] }
        : profile),
    })).toBeNull();
    const mutateFirstProfile = (
      mutation: (profile: (typeof catalog.profiles)[number]) => (typeof catalog.profiles)[number],
    ) => ({ ...catalog, profiles: catalog.profiles.map((profile, index) => index === 0 ? mutation(profile) : profile) });
    const mutateFirstStage = (
      mutation: (stage: (typeof catalog.profiles)[number]["stages"][number]) => (typeof catalog.profiles)[number]["stages"][number],
    ) => mutateFirstProfile((profile) => ({
      ...profile,
      stages: profile.stages.map((stage, index) => index === 0 ? mutation(stage) : stage),
    }));
    const retainedHashSubstitutions = [
      { ...catalog, registeredToolPageContractIds: [...catalog.registeredToolPageContractIds].reverse() },
      { ...catalog, profiles: [catalog.profiles[1], catalog.profiles[0], ...catalog.profiles.slice(2)] },
      mutateFirstProfile((profile) => ({ ...profile, title: `${profile.title} substituted` })),
      mutateFirstProfile((profile) => ({ ...profile, purpose: `${profile.purpose} substituted` })),
      mutateFirstProfile((profile) => ({ ...profile, expectedOutputs: ["Substituted output"] })),
      mutateFirstProfile((profile) => ({ ...profile, processForm: profile.processForm === "linear" ? "revisitable" : "linear" })),
      mutateFirstStage((stage) => ({ ...stage, stageKey: `${stage.stageKey}-substituted` })),
      mutateFirstProfile((profile) => ({
        ...profile,
        stages: profile.stages.length < 2 ? profile.stages : [
          { ...profile.stages[1]!, order: 1 },
          { ...profile.stages[0]!, order: 2 },
          ...profile.stages.slice(2),
        ],
      })),
      mutateFirstStage((stage) => ({ ...stage, pageContractId: "projects.html" })),
      mutateFirstStage((stage) => ({ ...stage, label: `${stage.label} substituted` })),
      mutateFirstStage((stage) => ({ ...stage, optional: !stage.optional })),
      mutateFirstStage((stage) => ({ ...stage, rationale: `${stage.rationale} substituted` })),
      mutateFirstStage((stage) => ({ ...stage, checkpointState: "required-human" })),
      mutateFirstStage((stage) => ({ ...stage, checkpointRationale: `${stage.checkpointRationale} substituted` })),
    ];
    for (const substituted of retainedHashSubstitutions) {
      expect(substituted.profileCatalogHash).toBe(catalog.profileCatalogHash);
      expect(decodeWorkflowProfileCatalogProjection(substituted)).toBeNull();
    }
    const requests: unknown[] = [];
    const client = createCoreApiClient(async (request) => {
      requests.push(request);
      return response(200, catalog);
    });
    await expect(client.workflowProfileCatalog()).resolves.toEqual(catalog);
    expect(requests).toEqual([{
      method: "GET",
      path: "/workflow-profiles/catalog",
      body: null,
      ifMatch: null,
      idempotencyKey: null,
    }]);
  });

  it("binds workflow progress reads and explicit human commands to exact authority", async () => {
    const stageRevisionId = "018f47a2-4d6b-7f78-9f2e-7fb76c86d071";
    const projection: WorkflowProgressProjection = {
      schemaVersion: "1.0",
      projectId: "01890f47-eae3-4cc0-98c4-dc0c0c073981",
      selectionRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d072",
      selectionRevisionContentHash: `sha256:${"a".repeat(64)}`,
      intentRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d070",
      intentRevisionContentHash: `sha256:${"d".repeat(64)}`,
      profileId: "hermeneutic-inquiry",
      profileTitle: "Hermeneutic inquiry",
      processForm: "revisitable",
      bootstrapRequired: false,
      current: {
        stageStateId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d073",
        stageStateRevisionId: stageRevisionId,
        revision: 1,
        revisionContentHash: `sha256:${"b".repeat(64)}`,
        parentStateRevisionId: null,
        stageKey: "intent-contract-1",
        pageContractId: "intent-contract.html",
        navigationRole: "primary",
        passNumber: 1,
        status: "current",
        completionEvidenceIds: [],
        attentionReason: null,
        staleCauseIds: [],
        skipRationale: null,
        updatedAt: "2026-09-04T02:00:00.000Z",
      },
      recommendedStageKey: "intent-contract-1",
      recommendedPageContractId: "intent-contract.html",
      recommendedAction: "Continue the current stage; completion requires explicit human evidence.",
      checkpointState: "unknown",
      checkpointRationale: "Checkpoint authority remains unknown until a later governed decision.",
      supportingHandoff: null,
      staleOutputs: [],
      history: [],
    };
    expect(decodeWorkflowProgressProjection(projection)).toEqual(projection);
    const bootstrap = {
      ...projection,
      bootstrapRequired: true,
      current: null,
      recommendedAction: "Start the guided workflow at this researcher-controlled stage.",
    };
    expect(decodeWorkflowProgressProjection(bootstrap)).toEqual(bootstrap);
    expect(decodeWorkflowProgressProjection({ ...projection, inventedAuthority: true })).toBeNull();
    expect(decodeWorkflowProgressProjection({
      ...projection,
      current: { ...projection.current!, stageStateRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d099" },
      supportingHandoff: {
        stageStateId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d074",
        stageStateRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d075",
        revisionContentHash: `sha256:${"c".repeat(64)}`,
        pageContractId: "project-settings.html",
        navigationRole: "supporting",
        returnStageStateRevisionId: stageRevisionId,
      },
    })).toBeNull();

    const requests: unknown[] = [];
    const client = createCoreApiClient(async (request) => {
      requests.push(request);
      return response(200, projection);
    });
    await expect(client.workflowProgress({ root: "C:/Research/study-one" })).resolves.toEqual(projection);
    await expect(client.commandWorkflowProgress({
      root: "C:/Research/study-one",
      action: "revisit",
      stageKey: "intent-contract-1",
      expectedSelectionRevisionId: projection.selectionRevisionId,
      expectedSelectionRevisionContentHash: projection.selectionRevisionContentHash,
      expectedStageStateRevisionId: stageRevisionId,
      expectedStageStateRevisionContentHash: projection.current!.revisionContentHash,
      revisitSourceStageStateRevisionId: stageRevisionId,
      revisitSourceStageStateRevisionContentHash: projection.current!.revisionContentHash,
      completionEvidenceRevisionIds: [],
      supportingPageContractId: null,
      rationale: null,
    }, "d".repeat(32))).resolves.toEqual(projection);
    expect(requests).toHaveLength(2);
    expect(requests[1]).toMatchObject({
      path: "/projects/workflow-progress/commands",
      idempotencyKey: "d".repeat(32),
    });
    await expect(client.commandWorkflowProgress({
      root: "C:/Research/study-one",
      action: "complete",
      stageKey: "intent-contract-1",
      expectedSelectionRevisionId: projection.selectionRevisionId,
      expectedSelectionRevisionContentHash: projection.selectionRevisionContentHash,
      expectedStageStateRevisionId: stageRevisionId,
      expectedStageStateRevisionContentHash: projection.current!.revisionContentHash,
      revisitSourceStageStateRevisionId: null,
      revisitSourceStageStateRevisionContentHash: null,
      completionEvidenceRevisionIds: [],
      supportingPageContractId: null,
      rationale: null,
    }, "e".repeat(32))).rejects.toThrow("RO-CORE-REQUEST-INVALID");
    await expect(client.commandWorkflowProgress({
      root: "C:/Research/study-one",
      action: "revisit",
      stageKey: "intent-contract-1",
      expectedSelectionRevisionId: projection.selectionRevisionId,
      expectedSelectionRevisionContentHash: projection.selectionRevisionContentHash,
      expectedStageStateRevisionId: stageRevisionId,
      expectedStageStateRevisionContentHash: projection.current!.revisionContentHash,
      revisitSourceStageStateRevisionId: stageRevisionId,
      revisitSourceStageStateRevisionContentHash: null,
      completionEvidenceRevisionIds: [],
      supportingPageContractId: null,
      rationale: null,
    }, "f".repeat(32))).rejects.toThrow("RO-CORE-REQUEST-INVALID");
  });

  it("keeps privacy changes consent-bound and cache deletion disclosure exact", async () => {
    const disclosure = {
      disclosureVersion: "secure-deletion-disclosure-v1",
      scope: "project-cache-only",
      logicalRemoval: true,
      physicalErasureGuaranteed: false,
      canonicalProjectDataExcluded: true,
      limitations: [
        "Filesystem unlink does not prove physical media erasure.",
        "SSD wear levelling can retain prior blocks.",
        "Journals, snapshots, backups, and hard links can retain copies.",
        "Only rebuildable project cache is cleared.",
      ],
    };
    const policy = {
      schemaVersion: "1.0",
      projectId: "11111111-1111-4111-8111-111111111111",
      revision: 1,
      defaultsApplied: false,
      networkPolicy: "approved-providers" as const,
      remoteModelApproval: "preview-every-task" as const,
      telemetryMode: "off" as const,
      logRetentionDays: 14,
      documentRetention: "project-lifetime" as const,
      cacheRetentionDays: 30,
      egressConsentRecorded: true,
      egressEnforcement: "require-task-preview" as const,
      deletionDisclosure: disclosure,
    };
    const token = "a".repeat(32);
    const preview = {
      schemaVersion: "1.0",
      projectId: policy.projectId,
      policyRevision: 1,
      previewToken: token,
      confirmation: `clear-cache:${token}`,
      expiresAt: "2026-08-22T00:05:00Z",
      itemCount: 2,
      byteCount: 19,
      deletionDisclosure: disclosure,
    };
    const result = {
      schemaVersion: "1.0",
      projectId: policy.projectId,
      state: "cleared" as const,
      itemCount: 2,
      byteCount: 19,
      cleanupPending: false,
      deletionDisclosure: disclosure,
    };
    expect(decodePrivacyPolicyProjection(policy)).toEqual(policy);
    expect(decodePrivacyPolicyProjection({ ...policy, egressConsentRecorded: false })).toBeNull();
    expect(decodePrivacyPolicyProjection({ ...policy, physicalErase: true })).toBeNull();
    expect(decodeCacheClearPreview(preview)).toEqual(preview);
    expect(decodeCacheClearPreview({ ...preview, confirmation: `clear-cache:${"b".repeat(32)}` })).toBeNull();
    expect(decodeCacheClearResult(result)).toEqual(result);
    expect(decodeCacheClearResult({ ...result, cleanupPending: true })).toBeNull();

    const requests: unknown[] = [];
    const responses = [policy, policy, preview, result];
    const client = createCoreApiClient(async (request) => {
      requests.push(request);
      return response(200, responses.shift());
    });
    await client.privacy({ root: "C:/Research/study-one" });
    await client.updatePrivacy({
      root: "C:/Research/study-one",
      expectedRevision: 0,
      networkPolicy: "approved-providers",
      remoteModelApproval: "preview-every-task",
      telemetryMode: "off",
      logRetentionDays: 14,
      documentRetention: "project-lifetime",
      cacheRetentionDays: 30,
      egressConsentToken: "acknowledge-egress-preview-v1",
    });
    await client.previewCache({ root: "C:/Research/study-one" });
    await client.clearCache({
      root: "C:/Research/study-one",
      previewToken: token,
      confirmation: `clear-cache:${token}`,
    });
    expect(requests.map((request) => (request as { path: string }).path)).toEqual([
      "/projects/privacy",
      "/projects/privacy/update",
      "/projects/privacy/cache/preview",
      "/projects/privacy/cache/clear",
    ]);
    await expect(client.updatePrivacy({
      root: "C:/Research/study-one",
      expectedRevision: 1,
      networkPolicy: "metadata-only",
      remoteModelApproval: "preview-every-task",
      telemetryMode: "off",
      logRetentionDays: 14,
      documentRetention: "project-lifetime",
      cacheRetentionDays: 30,
      egressConsentToken: null,
    })).rejects.toThrow("RO-CORE-REQUEST-INVALID");
  });

  it("binds intent drafts, exact impact acknowledgement, and non-launchable history", async () => {
    const current = {
      schemaVersion: "1.0",
      intentId: "01890f47-eae0-7cc0-98c4-dc0c0c07398f",
      revisionId: "01890f47-eae1-7cc0-98c4-dc0c0c07398f",
      revision: 1,
      revisionContentHash: `sha256:${"a".repeat(64)}`,
      createdAt: "2026-08-28T19:00:00Z",
      status: "draft",
      primaryUseCase: "theory-synthesis",
      epistemicMode: "theory",
      researchObjective: "",
      contributionIntent: "",
      phenomenon: "",
      unitOfAnalysis: "",
      levelOfAnalysis: "",
      sourceKinds: [],
      languageCodes: [],
      startYear: null,
      endYear: null,
      includePrivateReports: false,
      evidenceTypes: [],
      noveltyStandard: null,
      noveltyRationale: "",
      autonomyLevel: "suggest",
      stoppingConditions: ["interpretive-saturation"],
      revisionRationale: "Initial bounded draft.",
      unresolvedDecisions: ["research-question", "source-scope"],
      decisionComplete: false,
      canRequestAcceptance: false,
      launchReady: false,
    } as const;
    const summary = {
      revision: current.revision,
      revisionId: current.revisionId,
      revisionContentHash: current.revisionContentHash,
      createdAt: current.createdAt,
      status: current.status,
      primaryUseCase: current.primaryUseCase,
      unresolvedDecisionCount: current.unresolvedDecisions.length,
    };
    const workspace = {
      schemaVersion: "1.0",
      projectId: "11111111-1111-4111-8111-111111111111",
      current,
      history: [summary],
    };
    const impact = {
      schemaVersion: "1.0",
      expectedRevision: 1,
      changeCategories: ["corpus-scope"],
      affectedWorkflows: ["Search Studio"],
      affectedOutputs: ["Evidence Matrix"],
      affectedSchemas: ["research-intent-revision"],
      affectedCheckpoints: [],
      autonomyDefaultEffects: [],
      stoppingLogicEffects: [],
      staleArtifactIds: [],
      allToolsAccessible: true,
      evidenceRequirementsUnchanged: true,
      provenanceRequirementsUnchanged: true,
      warnings: ["Prior work is retained."],
      acknowledgementRequired: true,
      acknowledgementToken: "b".repeat(64),
    };
    const accepted = {
      ...current,
      revisionId: "01890f47-eae2-7cc0-98c4-dc0c0c07398f",
      revision: 2,
      revisionContentHash: `sha256:${"d".repeat(64)}`,
      createdAt: "2026-08-28T19:01:00Z",
      status: "accepted",
      unresolvedDecisions: [],
      decisionComplete: true,
      canRequestAcceptance: false,
      launchReady: true,
    } as const;
    const governing = {
      schemaVersion: "1.0",
      documentType: "research-observatory-research-intent-reference",
      contractVersion: "1.0.0",
      intentId: accepted.intentId,
      revisionId: accepted.revisionId,
      revision: accepted.revision,
      revisionContentHash: accepted.revisionContentHash,
    } as const;
    const decision = {
      schemaVersion: "1.0",
      decisionId: "01890f47-eae3-7cc0-98c4-dc0c0c07398f",
      evaluatedAt: "2026-08-28T19:02:00Z",
      action: "approve-claim",
      subjectType: "model",
      outcome: "require-confirmation",
      reasonCode: "claim-approval-requires-human-confirmation",
      explanation: "Claim approval remains under explicit human authority.",
      governingIntent: governing,
      requiredGates: ["claim-approval"],
      outputLabel: "theory-working-output",
      stoppingRequiresHumanConfirmation: true,
    } as const;
    expect(decodeIntentDraftProjection(current)).toEqual(current);
    expect(decodeIntentDraftProjection({ ...current, launchReady: true })).toBeNull();
    expect(decodeIntentWorkspaceProjection(workspace)).toEqual(workspace);
    expect(decodeIntentWorkspaceProjection({ ...workspace, history: [{ ...summary, revisionId: current.intentId }] })).toBeNull();
    expect(decodeIntentImpactPreview(impact)).toEqual(impact);
    expect(decodeIntentImpactPreview({ ...impact, acknowledgementToken: null })).toBeNull();
    expect(decodeIntentDraftProjection(accepted)).toEqual(accepted);
    expect(decodeIntentGoverningReference(governing)).toEqual(governing);
    expect(decodeIntentPolicyDecision(decision)).toEqual(decision);
    expect(decodeIntentPolicyDecision({ ...decision, outcome: "deny", outputLabel: decision.outputLabel })).toBeNull();

    const requests: unknown[] = [];
    const responses = [workspace, impact, current, accepted, decision];
    const client = createCoreApiClient(async (request) => {
      requests.push(request);
      return response(200, responses.shift());
    });
    await client.intent({ root: "C:/Research/study-one" });
    await client.previewIntent({
      root: "C:/Research/study-one",
      expectedRevision: 1,
      primaryUseCase: "systematic-review",
      sourceKinds: ["peer-reviewed-article"],
      languageCodes: ["en"],
      startYear: 2020,
      endYear: 2026,
      includePrivateReports: false,
      evidenceTypes: ["empirical-study"],
      noveltyStandard: "bounded-comparative",
      autonomyLevel: "suggest",
      stoppingConditions: ["coverage-threshold"],
    });
    await client.saveIntentDraft({
      root: "C:/Research/study-one",
      expectedRevision: 1,
      impactAcknowledgement: "b".repeat(64),
      primaryUseCase: "systematic-review",
      researchObjective: "What is known?",
      contributionIntent: "A bounded synthesis.",
      phenomenon: "Evidence use",
      unitOfAnalysis: "Study",
      levelOfAnalysis: "Field",
      sourceKinds: ["peer-reviewed-article"],
      evidenceTypes: ["empirical-study"],
      languageCodes: ["en"],
      startYear: 2020,
      endYear: 2026,
      includePrivateReports: false,
      noveltyStandard: "bounded-comparative",
      noveltyRationale: "Compare the nearest syntheses.",
      autonomyLevel: "suggest",
      stoppingConditions: ["coverage-threshold"],
      revisionRationale: "Refined after scope review.",
    }, "c".repeat(32));
    await client.acceptIntent({
      root: "C:/Research/study-one",
      expectedRevision: 1,
      expectedRevisionContentHash: current.revisionContentHash,
      confirmed: true,
      decisionRationale: "I reviewed and accept this exact revision.",
    }, "d".repeat(32));
    await client.evaluateIntentPolicy({
      root: "C:/Research/study-one",
      action: "approve-claim",
      subjectType: "model",
      stoppingCondition: null,
    });
    expect(requests.map((request) => (request as { path: string }).path)).toEqual([
      "/projects/intent", "/projects/intent/preview", "/projects/intent/drafts",
      "/projects/intent/acceptances", "/projects/intent/policy/evaluations",
    ]);
    expect(requests.at(-2)).toMatchObject({ idempotencyKey: "d".repeat(32) });
  });

  it("validates Task Center projections and binds commands to exact workflow authority", async () => {
    const workflow: WorkflowTaskCenterRun = {
      schemaVersion: "1.0",
      workflowRunId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d005",
      workflowKey: "source-review",
      definitionRevisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d002",
      definitionVersion: "1.0.0",
      snapshotId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d004",
      snapshotRevision: 1,
      continuationFromWorkflowRunId: null,
      continuationFromJobId: null,
      state: "waiting-human",
      activeCompute: false,
      progress: { kind: "quantified", unit: "steps", completedUnits: 1, totalUnits: 2 },
      revision: 28,
      interruptionKind: null,
      updatedAt: "2026-08-30T12:01:28.000Z",
      steps: [{ stepRunId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d011", stepKey: "review-source", kind: "human-task", state: "waiting-human", dependsOn: [] }],
      jobs: [],
      humanTasks: [{
        humanTaskId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d030",
        stepRunId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d011",
        state: "claimed",
        requiredRole: "researcher",
        assignedActorId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d041",
        requestedAt: "2026-08-30T12:01:25.000Z",
        evidenceArtifactIds: [],
        allowedDispositions: ["approved", "rejected"],
        consequencesByDisposition: { approved: "resume-workflow", rejected: "end-workflow" },
        decisionId: null,
        disposition: null,
        decidedAt: null,
      }],
      retainedArtifacts: [],
      events: [{ sequence: 28, entityType: "human-task", entityId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d030", toState: "claimed", occurredAt: "2026-08-30T12:01:28.000Z", reasonCode: "human-task-claimed" }],
    };
    expect(decodeWorkflowTaskCenterRun(workflow)).toEqual(workflow);
    expect(decodeWorkflowTaskCenterRun({ ...workflow, activeCompute: true })).toBeNull();
    expect(decodeWorkflowTaskCenterPage({ schemaVersion: "1.0", items: [workflow] })).not.toBeNull();
    const humanTask = workflow.humanTasks[0]!;
    const completedWithoutDecision = {
      ...humanTask,
      state: "completed",
      assignedActorId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d041",
    };
    expect(decodeWorkflowTaskCenterRun({ ...workflow, humanTasks: [completedWithoutDecision] })).toBeNull();
    expect(decodeWorkflowTaskCenterRun({
      ...workflow,
      humanTasks: [{ ...humanTask, decisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d031" }],
    })).toBeNull();
    expect(decodeWorkflowTaskCenterRun({
      ...workflow,
      humanTasks: [{
        ...humanTask,
        decisionId: "018f47a2-4d6b-7f78-9f2e-7fb76c86d031",
        disposition: "approved",
        decidedAt: "2026-08-30T12:01:29.000Z",
      }],
    })).toBeNull();
    expect(decodeWorkflowTaskCenterRun({
      ...workflow,
      humanTasks: [{ ...humanTask, assignedActorId: null }],
    })).toBeNull();
    expect(decodeWorkflowTaskCenterRun({ ...workflow, steps: [workflow.steps[0]!, workflow.steps[0]!] })).toBeNull();
    expect(decodeWorkflowTaskCenterRun({
      ...workflow,
      events: [
        { ...workflow.events[0]!, sequence: 29 },
        { ...workflow.events[0]!, sequence: 28 },
      ],
    })).toBeNull();

    const requests: unknown[] = [];
    const client = createCoreApiClient(async (request) => {
      requests.push(request);
      return request.method === "GET"
        ? response(200, { schemaVersion: "1.0", items: [workflow] })
        : response(200, workflow, "application/json", workflowEtag(workflow));
    });
    await client.taskCenter("C:/Research/study-one", 20);
    await client.cancelWorkflowJob(
      "C:/Research/study-one",
      "018f47a2-4d6b-7f78-9f2e-7fb76c86d006",
      workflow,
    );
    await client.retryWorkflowJob(
      "C:/Research/study-one",
      "018f47a2-4d6b-7f78-9f2e-7fb76c86d006",
      workflow,
      "b".repeat(32),
    );
    await client.decideWorkflowHumanTask(
      "C:/Research/study-one",
      workflow.humanTasks[0]!.humanTaskId,
      workflow,
      "approved",
      "a".repeat(32),
    );
    expect(requests[1]).toMatchObject({
      body: JSON.stringify({ root: "C:/Research/study-one", reasonCode: "user-requested" }),
      ifMatch: workflowEtag(workflow),
      idempotencyKey: null,
      path: "/projects/workflows/jobs/018f47a2-4d6b-7f78-9f2e-7fb76c86d006/cancel",
    });
    expect(requests[2]).toMatchObject({
      body: JSON.stringify({ root: "C:/Research/study-one" }),
      ifMatch: workflowEtag(workflow),
      idempotencyKey: "b".repeat(32),
      path: "/projects/workflows/jobs/018f47a2-4d6b-7f78-9f2e-7fb76c86d006/retry",
    });
    expect(requests[3]).toMatchObject({
      body: JSON.stringify({ root: "C:/Research/study-one", disposition: "approved" }),
      ifMatch: workflowEtag(workflow),
      idempotencyKey: "a".repeat(32),
      path: `/projects/workflows/human-tasks/${workflow.humanTasks[0]!.humanTaskId}/decide`,
    });
  });
});
