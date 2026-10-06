import { describe, expect, it } from "vitest";
import type { VersionContext } from "@research-observatory/contracts/core-api";
import {
  attachmentSelection,
  decodeAttachmentEvent,
  decodeAttachmentOutcome,
  sameAttachmentSelection,
  attachmentBeginRequest,
  attachmentCommitRequest,
  attachmentStatusRequest,
  isInterruptedPriorSessionStatus,
  canStartAttachmentReview,
  decodeAttachmentStatus,
  DOCUMENT_ATTACHMENT_COMMANDS,
  attachmentProblemMessage,
} from "./documentAttachment";

const projectId = "01900000-0000-7000-8000-000000000001";
const workA = "01900000-0000-7000-8000-000000000002";
const workB = "01900000-0000-7000-8000-000000000003";
const workRevisionA = "01900000-0000-7000-8000-000000000004";
const versionId = "01900000-0000-7000-8000-000000000005";
const versionRevisionId = "01900000-0000-7000-8000-000000000006";
const sourceId = "01900000-0000-7000-8000-000000000007";
const candidateId = "01900000-0000-7000-8000-000000000008";
const operationId = "01900000-0000-7000-8000-000000000009";
const commandId = "01900000-0000-7000-8000-000000000010";
const sessionId = "a".repeat(32);

describe("attachment failure evidence", () => {
  it("keeps a generic post-selection rejection distinct from evidence that no file was selected", () => {
    // The real Windows r01 transfer reached held staging before Core rejected
    // it. This fallback also serves failures before selection, so it cannot
    // infer either selection or durable attachment from the generic code.
    const message = attachmentProblemMessage("unavailable");
    expect(message).not.toMatch(/no file was selected|no file was attached/u);
    expect(message).toMatch(/current attachment status/u);
    expect(message).toMatch(/before retrying/u);
  });
});

function context(overrides: Partial<VersionContext> = {}): VersionContext {
  return {
    schemaVersion: "1.0", projectId, contextSha256: "b".repeat(64),
    works: [
      { schemaVersion: "1.0", workId: workA, revisionId: workRevisionA, previousRevisionId: null,
        decisionRevisionId: null, disposition: "active", aliasTarget: null, assertionRevisionIds: [sourceId] },
      { schemaVersion: "1.0", workId: workB, revisionId: "01900000-0000-7000-8000-000000000011", previousRevisionId: null,
        decisionRevisionId: null, disposition: "active", aliasTarget: null, assertionRevisionIds: [] },
    ],
    versions: [{ versionId, revisionId: versionRevisionId, previousRevisionId: null, decisionRevisionId: commandId,
      statusSha256: "c".repeat(64), definition: { kind: "accepted-manuscript", assertionRevisionIds: [sourceId], date: { precision: "not-reported", value: null } } }],
    placements: [{ versionId, state: "assigned", workIds: [workA] }],
    sources: [{ assertionRevisionId: sourceId, assertion: { projectId } } as VersionContext["sources"][number]],
    preferenceStates: [], preferences: [], relations: [], ...overrides,
  };
}

describe("selected-version attachment identity", () => {
  it("binds the clicked version to one current Work revision and an explicit member assertion", () => {
    const selection = attachmentSelection(context(), versionId, sourceId);
    expect(selection).toEqual({ projectId, workId: workA, workRevisionId: workRevisionA,
      versionId, versionRevisionId, sourceAssertionRevisionId: sourceId });
    expect(attachmentSelection(context(), versionId, "")).toBeNull();
    expect(attachmentSelection(context(), "missing", sourceId)).toBeNull();
  });

  it("refuses ambiguous placement, alien assertions, changed Work and version revisions", () => {
    const current = context();
    const selected = attachmentSelection(current, versionId, sourceId)!;
    expect(attachmentSelection(context({ placements: [{ versionId, state: "assigned", workIds: [workA, workB] }] }), versionId, sourceId)).toBeNull();
    expect(attachmentSelection(context({ placements: [{ versionId, state: "assigned", workIds: [workA] },
      { versionId, state: "assigned", workIds: [workB] }] }), versionId, sourceId)).toBeNull();
    expect(attachmentSelection(context({ placements: [{ versionId, state: "requires-review", workIds: [workA] }] }), versionId, sourceId)).toBeNull();
    expect(attachmentSelection(context({ works: current.works.map((work) => work.workId === workA ? { ...work, assertionRevisionIds: [] } : work) }), versionId, sourceId)).toBeNull();
    const changedWork = context({ works: current.works.map((work) => work.workId === workA ? { ...work, revisionId: workB } : work) });
    expect(sameAttachmentSelection(selected, attachmentSelection(changedWork, versionId, sourceId))).toBe(false);
    const changedVersion = context({ versions: current.versions.map((version) => ({ ...version, revisionId: workB })) });
    expect(sameAttachmentSelection(selected, attachmentSelection(changedVersion, versionId, sourceId))).toBe(false);
  });
});

describe("opaque native attachment contract", () => {
  const selection = attachmentSelection(context(), versionId, sourceId)!;
  it("freezes exact choose/drop and commit payloads without a renderer source path or bytes", () => {
    expect(attachmentBeginRequest("choose", operationId, selection)).toEqual({ schemaVersion: "1.0", mode: "choose", operationId, selection });
    expect(attachmentBeginRequest("drop", operationId, selection).mode).toBe("drop");
    const request = attachmentCommitRequest(operationId, sessionId, candidateId, "d".repeat(64), commandId, selection);
    expect(request).toEqual({ schemaVersion: "1.0", operationId, sessionId, candidateId,
      confirmationSha256: "d".repeat(64), commandId, selection, matchConfirmed: true, permittedUse: "project-only" });
    expect(JSON.stringify(request)).not.toMatch(/sourcePath|filePath|base64|bytes|blob|handle/u);
  });

  it("accepts only a correlated, safe candidate event and rejects extra fields", () => {
    const event = { schemaVersion: "1.0", status: "candidate", operationId, sessionId, selection,
      candidate: { candidateId, sourceName: "paper.pdf", byteLength: 42, format: "pdf", confirmationSha256: "d".repeat(64), confirmationRequired: true } };
    expect(decodeAttachmentEvent(event)).toEqual(event);
    expect(decodeAttachmentEvent({ ...event, filePath: "C:/private/paper.pdf" })).toBeNull();
    expect(decodeAttachmentEvent({ ...event, candidate: { ...event.candidate, sourceName: "C:/private/paper.pdf" } })).toBeNull();
    expect(decodeAttachmentEvent({ ...event, candidate: { ...event.candidate, bytes: [1, 2] } })).toBeNull();
    expect(decodeAttachmentEvent({ ...event, selection: { ...selection, versionRevisionId: workB } })).not.toBeNull();
  });

  it("accepts only exact-revision committed results and bounded denial codes", () => {
    const attached = { schemaVersion: "1.0", status: "attached", operationId, sessionId, selection, candidateId,
      attachmentId: "01900000-0000-7000-8000-000000000012", documentRevisionId: "01900000-0000-7000-8000-000000000013" };
    expect(decodeAttachmentOutcome(attached)).toEqual(attached);
    expect(decodeAttachmentOutcome({ ...attached, path: "C:/private/paper.pdf" })).toBeNull();
    expect(decodeAttachmentOutcome({ schemaVersion: "1.0", status: "rejected", operationId, sessionId, selection,
      code: "password-protected" })).not.toBeNull();
    expect(decodeAttachmentOutcome({ schemaVersion: "1.0", status: "rejected", operationId, sessionId, selection,
      code: "arbitrary-server-message" })).toBeNull();
  });
  it("freezes exact-ID status route and rejects untrusted status fields or missing reader identity", () => {
    expect(DOCUMENT_ATTACHMENT_COMMANDS.status).toBe("document_attachment_status");
    expect(attachmentStatusRequest(selection, operationId, commandId)).toEqual({
      schemaVersion: "1.0", selection, operationId, commandId,
    });
    const durable = { schemaVersion: "1.0", status: "processing", selection, operationId, commandId,
      attachmentId: "01900000-0000-7000-8000-000000000012", documentRevisionId: "01900000-0000-7000-8000-000000000013", code: null,
      retryRequest: null };
    expect(decodeAttachmentStatus(durable)).toEqual(durable);
    expect(decodeAttachmentStatus({ ...durable, sourcePath: "C:/private/paper.pdf" })).toBeNull();
    expect(decodeAttachmentStatus({ ...durable, attachmentId: null })).toBeNull();
    expect(decodeAttachmentStatus({ ...durable, status: "unknown-native-state" })).toBeNull();
    expect(decodeAttachmentStatus({ ...durable, operationId: null })).toBeNull();
    expect(decodeAttachmentStatus({ ...durable, status: "unconfirmed", attachmentId: null, documentRevisionId: null, commandId: null })).toBeNull();
    expect(decodeAttachmentStatus({ ...durable, status: "unconfirmed", attachmentId: null, documentRevisionId: null })).toBeNull();
    const retryRequest = attachmentCommitRequest(operationId, sessionId, candidateId, "d".repeat(64), commandId, selection);
    expect(decodeAttachmentStatus({ ...durable, status: "unconfirmed", attachmentId: null, documentRevisionId: null,
      retryRequest })).not.toBeNull();
    expect(decodeAttachmentStatus({ ...durable, status: "unconfirmed", attachmentId: null, documentRevisionId: null,
      retryRequest: { ...retryRequest, sourcePath: "C:/private/paper.pdf" } })).toBeNull();
    expect(decodeAttachmentStatus({ ...durable, status: "denied", attachmentId: null, documentRevisionId: null, code: null })).toBeNull();
    expect(decodeAttachmentStatus({ ...durable, status: "metadata-only", attachmentId: null, documentRevisionId: null })).toEqual({
      ...durable, status: "metadata-only", attachmentId: null, documentRevisionId: null,
    });
  });
  it("releases only an exact saved command on a terminal prior-session result without replay", () => {
    const saved = attachmentCommitRequest(operationId, sessionId, candidateId, "d".repeat(64), commandId, selection);
    const request = attachmentStatusRequest(selection, operationId, commandId);
    const terminal = { schemaVersion: "1.0" as const, status: "unavailable" as const, selection,
      operationId, commandId: null, attachmentId: null, documentRevisionId: null,
      code: "interrupted" as const, retryRequest: null };
    expect(isInterruptedPriorSessionStatus(saved, request, terminal)).toBe(true);
    expect(isInterruptedPriorSessionStatus(saved, request, terminal, true)).toBe(false);
    expect(isInterruptedPriorSessionStatus(null, request, terminal)).toBe(false);
    expect(isInterruptedPriorSessionStatus(saved, { ...request, commandId: workB }, terminal)).toBe(false);
    expect(isInterruptedPriorSessionStatus(saved, request, { ...terminal, operationId: workB })).toBe(false);
    expect(isInterruptedPriorSessionStatus(saved, request, { ...terminal,
      selection: { ...selection, workRevisionId: workB } })).toBe(false);
    expect(isInterruptedPriorSessionStatus(saved, request, { ...terminal, code: "candidate-unavailable" })).toBe(false);
    expect(isInterruptedPriorSessionStatus(saved, request, { ...terminal, status: "processing" })).toBe(false);
    expect(isInterruptedPriorSessionStatus(saved, request, { ...terminal, retryRequest: saved })).toBe(false);
    expect(isInterruptedPriorSessionStatus(saved, request, { ...terminal, attachmentId: workB })).toBe(false);
  });
  it("allows a fresh review after terminal recoverable status but holds denial and active operations", () => {
    const baseline = { schemaVersion: "1.0" as const, selection, operationId, commandId: null,
      attachmentId: null, documentRevisionId: null, code: null, retryRequest: null };
    expect(canStartAttachmentReview(null)).toBe(false);
    expect(canStartAttachmentReview({ ...baseline, status: "metadata-only" })).toBe(true);
    expect(canStartAttachmentReview({ ...baseline, status: "cancelled" })).toBe(true);
    expect(canStartAttachmentReview({ ...baseline, status: "cancelled", code: "rights-denied" })).toBe(false);
    expect(canStartAttachmentReview({ ...baseline, status: "failed", code: "unsafe-content" })).toBe(true);
    expect(canStartAttachmentReview({ ...baseline, status: "failed", code: "password-protected" })).toBe(true);
    expect(canStartAttachmentReview({ ...baseline, status: "unavailable", code: "worker-unavailable" })).toBe(true);
    expect(canStartAttachmentReview({ ...baseline, status: "unavailable", code: "storage-pressure" })).toBe(true);
    expect(canStartAttachmentReview({ ...baseline, status: "unavailable", code: "unsafe-content" })).toBe(false);
    expect(canStartAttachmentReview({ ...baseline, status: "failed", code: "rights-denied" })).toBe(false);
    expect(canStartAttachmentReview({ ...baseline, status: "denied", code: "rights-denied" })).toBe(false);
    expect(canStartAttachmentReview({ ...baseline, status: "failed", code: "authority-changed" })).toBe(false);
    expect(canStartAttachmentReview({ ...baseline, status: "candidate" })).toBe(false);
    expect(canStartAttachmentReview({ ...baseline, status: "validating" })).toBe(false);
  });
});
