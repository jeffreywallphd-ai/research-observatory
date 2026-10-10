import { describe, expect, it } from "vitest";
import { decodeReaderAction, type ReaderActionRequest } from "./viewerActions";
import type { ViewerMetadata } from "./documentViewer";

const id = (n: number): string => `00000000-0000-7000-8000-${n.toString().padStart(12, "0")}`;
const source = { projectId: id(1), attachmentId: id(2), documentRevisionId: id(3), documentId: id(4), candidateId: id(5),
  sourceAssertionRevisionId: id(6), workId: id(7), workRevisionId: id(8), versionId: id(9), versionRevisionId: id(10),
  objectSha256: "a".repeat(64), byteLength: 100, format: "pdf" as const, provenance: { kind: "local-import" as const } };
const metadata: ViewerMetadata = { source, normalizedRevisionId: id(11) };
const request: ReaderActionRequest = { schemaVersion: "1.0", projectId: source.projectId,
  selector: { attachmentId: source.attachmentId, documentRevisionId: source.documentRevisionId, normalizedRevisionId: id(11) },
  operationId: id(12), stage: "policy", action: "copy-quotation", anchorId: id(13), expectedPolicyRevisionId: null, commandId: null, confirmed: false };
const decision = { schemaVersion: "1.0", metadata, action: request.action, anchorId: request.anchorId, policyRevisionId: id(14),
  state: "review-required", reasonCode: "rights-assertion-missing", canReview: true, selectionLimitCodepoints: 2048,
  requirements: [...["inspect", "derive"].map(action => ({ use: { action, purpose: "document-analysis", destinationKind: "local-project" }, code: "allow", reasonCode: "rights-permitted" })),
    { use: { action: "quote", purpose: "viewer-quotation", destinationKind: "local-project" }, code: "unknown", reasonCode: "rights-assertion-missing" },
    { use: { action: "export", purpose: "viewer-copy-quotation", destinationKind: "local-export" }, code: "unknown", reasonCode: "rights-assertion-missing" }] };
decision.requirements = decision.requirements.map(item => ({ ...item, use: { ...item.use, provider: null, region: null, shareGroup: null } }));
const outcome = { schemaVersion: "1.0", projectId: request.projectId, operationId: request.operationId, action: request.action,
  status: "policy", drained: true, decision, review: null };

describe("Reader action delivery contract", () => {
  it("retains source permission review as a separate non-executing disposition", () => {
    expect(decodeReaderAction(outcome, request, metadata)?.decision?.canReview).toBe(true);
    expect(decodeReaderAction({ ...outcome, status: "completed", decision: null }, request, metadata)).toBeNull();
    const execution = { ...request, stage: "execute" as const, confirmed: true, expectedPolicyRevisionId: id(14) };
    expect(decodeReaderAction({ ...outcome, status: "completed", decision: null }, execution, metadata)?.status).toBe("completed");
  });
  it("denies wrong source, accepted revision, anchor, operation and policy shapes", () => {
    for (const changed of [{ ...outcome, operationId: id(90) }, { ...outcome, projectId: id(91) },
      { ...outcome, decision: { ...decision, anchorId: id(92) } },
      { ...outcome, decision: { ...decision, metadata: { ...metadata, normalizedRevisionId: id(93) } } },
      { ...outcome, decision: { ...decision, metadata: { ...metadata, source: { ...source, candidateId: id(94) } } } },
      { ...outcome, decision: { ...decision, state: "ready", canReview: true } }]) {
      expect(decodeReaderAction(changed, request, metadata)).toBeNull();
    }
  });
  it("does not admit quotation, paths, destination claims, grants or executable details", () => {
    for (const field of ["text", "contentUtf8", "root", "actorId", "destination", "applicationPath"]) {
      expect(decodeReaderAction({ ...outcome, [field]: "untrusted" }, request, metadata)).toBeNull();
      expect(decodeReaderAction({ ...outcome, decision: { ...decision, [field]: "untrusted" } }, request, metadata)).toBeNull();
    }
    const getter = Object.defineProperty({ ...outcome }, "status", { get: () => { throw new Error("must not read accessors"); } });
    expect(decodeReaderAction(getter, request, metadata)).toBeNull();
  });
  it("accepts unknown closure only as unavailable and never as successful delivery", () => {
    expect(decodeReaderAction({ ...outcome, drained: false }, request, metadata)).toBeNull();
    const unknown = decodeReaderAction({ ...outcome, status: "unavailable", drained: false, decision: null }, request, metadata);
    expect(unknown?.drained).toBe(false);
    expect(decodeReaderAction({ ...outcome, status: "recorded", decision: null, review: {
      schemaVersion: "1.0", metadata, action: request.action, policyRevisionId: id(14), status: "recorded",
    } }, { ...request, stage: "rights-review", anchorId: null, commandId: id(15), confirmed: true }, metadata)?.status).toBe("recorded");
  });
  it("rejects broad or reordered permission purposes and preserves partial output outcomes", () => {
    for (const requirements of [decision.requirements.slice(0, 2), [...decision.requirements].reverse(),
      decision.requirements.map(v => ({ ...v, use: { ...v.use, purpose: "project-export" } })),
      decision.requirements.map(v => ({ ...v, use: { ...v.use, provider: "remote-provider" } }))]) {
      expect(decodeReaderAction({ ...outcome, decision: { ...decision, requirements } }, request, metadata)).toBeNull();
    }
    const execution = { ...request, stage: "execute" as const, confirmed: true, expectedPolicyRevisionId: id(14) };
    expect(decodeReaderAction({ ...outcome, status: "partial", decision: null }, execution, metadata)?.status).toBe("partial");
    expect(decodeReaderAction({ ...outcome, status: "partial", decision: null }, request, metadata)).toBeNull();
  });
});
