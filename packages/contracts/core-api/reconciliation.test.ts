import { describe, expect, it } from "vitest";
import { createCoreApiClient, decodeCandidatePage, decodeReconciliationBatchStatus } from "./generated";

const id = "01900000-0000-7000-8000-000000000001";
const other = "01900000-0000-7000-8000-000000000002";
const root = "C:/Research/synthetic";
const configuration = "b3e04c16bcfbb8588a718d55a94217a21a02ba1877fa9ea6ba187ebcdfc98dfc";
const status = () => ({ requestId: id, jobId: id, workflowRunId: id, state: "succeeded", setRevisionId: id, diagnosticCode: null });
const page = () => ({ schemaVersion: "1.0", projectId: id, setRevisionId: id, requestId: id,
  inventorySha256: "a".repeat(64), currentInventorySha256: "a".repeat(64), inventoryState: "unchanged",
  recordCount: 0, candidateCount: 0, comparedPairs: 0, membershipState: "unchanged", dependencyState: "unaffected",
  algorithm: "scholarly-duplicate-ranking/1.0.0", featureVersion: "scholarly-duplicate-features/1.0.0",
  configurationSha256: configuration, identifierNormalizer: "scholarly-identifiers/1.0.0", after: 0, nextAfter: null, items: [] });
const response = (value: unknown) => ({ status: 200, contentType: "application/json", traceId: "a".repeat(32), etag: null, body: JSON.stringify(value) });

describe("bounded scholarly reconciliation client", () => {
  it("rejects false success and false snapshot freshness", () => {
    expect(decodeReconciliationBatchStatus(status())).toEqual(status());
    expect(decodeReconciliationBatchStatus({ ...status(), setRevisionId: null })).toBeNull();
    expect(decodeReconciliationBatchStatus({ ...status(), state: "running" })).toBeNull();
    expect(decodeCandidatePage(page())).toEqual(page());
    expect(decodeCandidatePage({ ...page(), currentInventorySha256: "b".repeat(64) })).toBeNull();
    expect(decodeCandidatePage({ ...page(), candidateCount: 1 })).toBeNull();
    expect(decodeCandidatePage({ ...page(), actorId: id })).toBeNull();
    expect(decodeCandidatePage({ ...page(), configurationSha256: "0".repeat(64) })).toBeNull();
  });

  it("binds batch and page replies to exact requested identities", async () => {
    let value: unknown = status();
    const paths: string[] = [];
    const client = createCoreApiClient(async (request) => { paths.push(request.path); return response(value); });
    await expect(client.inspectScholarlyReconciliationBatch({ root, requestId: id, jobId: id })).resolves.toEqual(status());
    value = { ...status(), jobId: other };
    await expect(client.inspectScholarlyReconciliationBatch({ root, requestId: id, jobId: id })).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
    value = page();
    await expect(client.inspectScholarlyDuplicateCandidates({ root, setRevisionId: id, after: 0, limit: 25 })).resolves.toEqual(page());
    value = { ...page(), setRevisionId: other };
    await expect(client.inspectScholarlyDuplicateCandidates({ root, setRevisionId: id, after: 0, limit: 25 })).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
    expect(paths).toHaveLength(4);
  });

  it("rejects untrusted request authority and malformed pages before transport", async () => {
    let calls = 0, getterCalls = 0;
    const client = createCoreApiClient(async () => { calls += 1; return response({ requestId: id }); });
    await expect(client.prepareScholarlyReconciliationBatch({ root })).resolves.toEqual({ requestId: id });
    await expect(client.prepareScholarlyReconciliationBatch({ root, actorId: id } as any)).rejects.toThrow("RO-CORE-REQUEST-INVALID");
    await expect(client.inspectScholarlyDuplicateCandidates({ root, setRevisionId: id, after: 0, limit: 101 })).rejects.toThrow("RO-CORE-REQUEST-INVALID");
    await expect(client.prepareScholarlyReconciliationBatch({ get root() { getterCalls += 1; return root; } })).rejects.toThrow("RO-CORE-REQUEST-INVALID");
    expect(calls).toBe(1); expect(getterCalls).toBe(0);
  });
});
