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
  decodeVersionResponse,
  decodeWorkflowTaskCenterPage,
  decodeWorkflowTaskCenterRun,
  evaluateCoreApiCompatibility,
  parseOperationEventStream,
  type CoreApiResponse,
  type ProvenanceLineagePage,
  type VersionResponse,
  type WorkflowTaskCenterRun,
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
      templateId: "theory-synthesis",
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
      templateId: "theory-synthesis",
    });
    await expect(client.openProject({ root: "relative/project" })).rejects.toThrow("RO-CORE-REQUEST-INVALID");
    await expect(client.deleteProject({ root: projection.root, confirmation: "delete:wrong" })).rejects.toThrow(
      "RO-CORE-REQUEST-INVALID",
    );
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
      noveltyStandard: "bounded-comparative",
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
