import { describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { createCoreApiClient, decodeConnectorCapabilities, decodeConnectorInspection, decodeConnectorRecentRuns, sourceTestCommand, type ConnectorCapabilities, type CoreApiResponse } from "./generated";
const provider: ConnectorCapabilities = { schemaVersion: "1.0", providerId: "unpaywall", adapterVersion: "1.0.0", sourceApiVersion: "2", operations: ["oa-resolution"], identifierSchemes: ["doi"], maximumPageSize: 1, configuration: "ready", requiredSettings: ["contact"] };
const projectId = "01900000-0000-4000-8000-000000000001";
const id = "01900000-0000-7000-8000-000000000001";
const root = "C:/Research/synthetic";
const command = () => sourceTestCommand(root, projectId, provider, "10.99999/synthetic", id);
const response = (body: unknown): CoreApiResponse => ({ status: 200, contentType: "application/json", traceId: "a".repeat(32), etag: null, body: JSON.stringify(body) });
function preview() { const c = command(); return { previewId: id, request: c.request, retention: c.retention, requestSha256: "sha256:" + "b".repeat(64), destinationHost: "api.unpaywall.org", terms: { license: { state: "unknown", value: null }, terms: { state: "reported", value: "https://data.unpaywall.org/products/api" }, access: "unknown" }, intentRevisionId: id, intentSha256: "sha256:" + "c".repeat(64), policySha256: "sha256:" + "d".repeat(64), expiresAt: "2026-09-24T12:00:00Z", confirmation: "synthetic-confirmation" }; }
const run = () => ({ previewId: id, invocationId: id, jobId: id, workflowRunId: id, providerId: "unpaywall", operation: "oa-resolution", state: "failed", updatedAt: "2026-09-24T12:00:00.000Z", diagnosticCode: "connector-provider-unavailable" });
const inspection = () => ({ job: run(), queryJson: JSON.stringify(command().request.query), scientificRequestSha256: "sha256:" + "a".repeat(64), observation: null, recordOffset: 0, nextRecordOffset: null });
describe("scholarly source client", () => {
  it("rejects duplicate and secret-bearing capability projections", () => {
    expect(decodeConnectorCapabilities({ items: [provider] })).not.toBeNull();
    expect(decodeConnectorCapabilities({ items: [provider, provider] })).toBeNull();
    expect(decodeConnectorCapabilities({ items: [{ ...provider, key: "synthetic" }] })).toBeNull();
  });
  it("constructs a bounded one-DOI request with no inferred downstream rights", () => {
    expect(command()).toEqual(JSON.parse(readFileSync(new URL("../../../tests/fixtures/scholarly-metadata/source-test-request.v1.json", import.meta.url), "utf8")));
    expect(command().request.query).toEqual({ kind: "oa-resolution", identifier: { scheme: "doi", value: "10.99999/synthetic" } });
    expect(command().retention.rights["model-use"].value).toBe("unknown");
    expect(command().request.policy.maximumAttempts).toBe(1);
    expect(() => sourceTestCommand(root, projectId, { ...provider, configuration: "not-configured" }, "10.99999/synthetic", id)).toThrow();
    expect(() => sourceTestCommand(root, projectId, provider, "https://private.invalid/", id)).toThrow();
  });
  it("binds previews to the complete original request, retention and fixed destination", async () => {
    const transport = vi.fn(async () => response(preview()));
    const client = createCoreApiClient(transport);
    expect((await client.previewSourceTest(command())).previewId).toBe(id);
    expect(transport.mock.calls).toHaveLength(1);
    for (const mutate of [(p: ReturnType<typeof preview>) => { p.destinationHost = "untrusted.invalid"; }, (p: ReturnType<typeof preview>) => { p.request = { ...p.request, projectId: id }; }, (p: ReturnType<typeof preview>) => { p.retention = { ...p.retention, retainBody: false }; }]) {
      const changed = preview(); mutate(changed); transport.mockResolvedValueOnce(response(changed));
      await expect(client.previewSourceTest(command())).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
    }
  });
  it("retains bounded provider failure and rejects substituted job identity", async () => {
    const status = { jobId: id, workflowRunId: id, state: "failed", diagnosticCode: "connector-provider-unavailable" };
    const transport = vi.fn(async () => response(status)); const client = createCoreApiClient(transport);
    expect((await client.sourceTestStatus({ root, jobId: id })).diagnosticCode).toBe(status.diagnosticCode);
    transport.mockResolvedValueOnce(response({ ...status, jobId: "01900000-0000-7000-8000-000000000002" }));
    await expect(client.cancelSourceTest({ root, jobId: id })).rejects.toThrow();
  });
  it("does not retry an ambiguous confirmation", async () => {
    const transport = vi.fn(async () => { throw new Error("synthetic transport loss"); });
    await expect(createCoreApiClient(transport).confirmSourceTest({ root, previewId: id, confirmation: "synthetic-confirmation" })).rejects.toThrow();
    expect(transport).toHaveBeenCalledTimes(1);
  });
  it("validates bounded historical inspections and exact lookup identity without sending", async () => {
    expect(decodeConnectorRecentRuns({ items: [run()], scope: "latest-20-source-jobs-within-100-workflows" })).not.toBeNull();
    expect(decodeConnectorInspection(inspection())).not.toBeNull();
    for (const extra of [{ confirmation: "synthetic" }, { nextRecordOffset: 1 }, { queryJson: '{"kind":"lookup"}' }, { observation: {} }]) {
      expect(decodeConnectorInspection({ ...inspection(), ...extra })).toBeNull();
    }
    const transport = vi.fn(async () => response(inspection()));
    const client = createCoreApiClient(transport);
    expect((await client.inspectSourceRequest({ root, previewId: id, recordOffset: 0 }))?.job.jobId).toBe(id);
    expect(transport.mock.calls).toHaveLength(1);
    transport.mockResolvedValueOnce(response({ ...inspection(), job: { ...run(), previewId: "01900000-0000-7000-8000-000000000002" } }));
    await expect(client.inspectSourceRequest({ root, previewId: id, recordOffset: 0 })).rejects.toThrow();
    transport.mockResolvedValueOnce(response(null));
    expect(await client.inspectSourceRequest({ root, previewId: id, recordOffset: 0 })).toBeNull();
  });
});
