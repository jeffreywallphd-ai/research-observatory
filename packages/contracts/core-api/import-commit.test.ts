import { describe, expect, it } from "vitest";
import { createCoreApiClient, decodeImportCommitStatus, decodeImportManifest, decodeImportManifestPage } from "./generated";

const id = "01900000-0000-7000-8000-000000000001";
const other = "01900000-0000-7000-8000-000000000002";
const address = { root: "C:/Research/synthetic", previewId: id };
const manifest = () => ({ projectId: id, revisionId: id, aggregateId: id, previewId: id, draftRevision: 1,
  sourceSha256: "a".repeat(64), identitySha256: "b".repeat(64), effectiveDraftSha256: "c".repeat(64), parserVersion: "reference-import/1",
  mappingId: id, mappingRevision: 1, previousManifestRevisionId: null, recordCount: 2, selectedCount: 1,
  createdCount: 1, reusedCount: 0, membersSha256: "d".repeat(64), createdAt: "2026-09-20T00:00:00.000Z" });
const status = () => ({ previewId: id, requestId: id, jobId: id, jobState: "succeeded", diagnosticCode: null, manifest: manifest() });
const page = () => ({ previewId: id, revisionId: id, records: [{ ordinal: 1, recordKey: "a".repeat(64), included: true,
  sourceRecordRevisionId: id, warnings: [], comparison: "not-compared", previousRecordRevisionId: null }], nextAfter: 1, complete: false });
const response = (value: unknown) => ({ status: 200, contentType: "application/json", traceId: "a".repeat(32), etag: null, body: JSON.stringify(value) });

describe("canonical import commit transport", () => {
  it("rejects inconsistent counts and false accepted output while owning decoded data", () => {
    expect(decodeImportManifest(manifest())).not.toBeNull();
    expect(decodeImportManifest({ ...manifest(), selectedCount: 3 })).toBeNull();
    expect(decodeImportManifest({ ...manifest(), reusedCount: 1 })).toBeNull();
    expect(decodeImportCommitStatus({ ...status(), manifest: null })).toBeNull();
    expect(decodeImportCommitStatus({ ...status(), jobState: "running" })).toBeNull();
    expect(decodeImportCommitStatus({ ...status(), jobId: null })).toBeNull();
    const value = status(), decoded = decodeImportCommitStatus(value);
    value.manifest.createdCount = 0;
    expect(decoded?.manifest?.createdCount).toBe(1);
    expect(Object.isFrozen(decoded?.manifest)).toBe(true);
    // Scientific reuse can point to another preview's immutable original manifest.
    expect(decodeImportCommitStatus({ ...status(), manifest: { ...manifest(), previewId: other } })).not.toBeNull();
  });
  it("validates member identities, contiguous cursor and comparison provenance", () => {
    expect(decodeImportManifestPage(page())).not.toBeNull();
    expect(decodeImportManifestPage({ ...page(), nextAfter: 2 })).toBeNull();
    expect(decodeImportManifestPage({ ...page(), records: [] })).toBeNull();
    for (const changed of [{ included: false }, { sourceRecordRevisionId: null }, { comparison: "updated" }, { previousRecordRevisionId: id }]) {
      expect(decodeImportManifestPage({ ...page(), records: [{ ...page().records[0], ...changed }] })).toBeNull();
    }
  });
  it("binds delayed replies to the owned request and rejects another job cancellation", async () => {
    let resolve!: (value: ReturnType<typeof response>) => void;
    const client = createCoreApiClient(async () => new Promise((done) => { resolve = done; }));
    const command = { ...address, requestId: id };
    const pending = client.importCommitStatus(command);
    command.requestId = other;
    resolve(response({ ...status(), requestId: other }));
    await expect(pending).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
    const cancel = client.cancelImportCommit({ ...address, requestId: id, jobId: other });
    resolve(response(status()));
    await expect(cancel).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
  });
  it("distinguishes absent manifests and enforces header/page response binding", async () => {
    let value: unknown = null;
    const client = createCoreApiClient(async () => response(value));
    await expect(client.importManifest({ ...address, revisionId: null })).resolves.toBeNull();
    value = manifest();
    await expect(client.importManifest({ ...address, revisionId: id })).resolves.toEqual(manifest());
    await expect(client.importManifest({ ...address, revisionId: other })).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
    value = page();
    await expect(client.importManifestMembers({ ...address, revisionId: id, after: 0, limit: 1 })).resolves.toEqual(page());
    await expect(client.importManifestMembers({ ...address, revisionId: id, after: 1, limit: 1 })).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
  });
  it("discovers saved requests without executing and validates Core-minted preparation", async () => {
    let value: unknown = null;
    const paths: string[] = [];
    const client = createCoreApiClient(async (request) => { paths.push(request.path); return response(value); });
    await expect(client.latestImportCommit(address)).resolves.toBeNull();
    value = { ...status(), jobId: null, jobState: null, manifest: null };
    await expect(client.prepareImportCommit({ ...address, revision: 1, previousManifestRevisionId: null })).resolves.toEqual(value);
    await expect(client.latestImportCommit(address)).resolves.toEqual(value);
    expect(paths).toEqual(["/projects/imports/commit/latest", "/projects/imports/commit/prepare", "/projects/imports/commit/latest"]);
  });
  it("rejects unbounded requests and extra authority without invoking transport", async () => {
    let calls = 0;
    const client = createCoreApiClient(async () => { calls += 1; return response(status()); });
    await expect(client.startImportCommit({ ...address, requestId: id, revision: 1, previousManifestRevisionId: null })).resolves.toEqual(status());
    await expect(client.startImportCommit({ ...address, requestId: id, revision: 0, previousManifestRevisionId: null })).rejects.toThrow("RO-CORE-REQUEST-INVALID");
    await expect(client.importCommitStatus({ ...address, requestId: id, actorId: id } as any)).rejects.toThrow("RO-CORE-REQUEST-INVALID");
    await expect(client.importManifestMembers({ ...address, revisionId: id, after: 0, limit: 101 })).rejects.toThrow("RO-CORE-REQUEST-INVALID");
    expect(calls).toBe(1);
  });
});
