import { describe, expect, it } from "vitest";
import { createCoreApiClient, decodeReviewSummary, decodeReviewPage, decodeReviewDetail, decodeDiagnosticPage, decodeImportPreviewItem, decodeImportPreviewPage } from "./generated";

const previewId = "01900000-0000-7000-8000-000000000001";
const address = { root: "C:/Research/synthetic", previewId };
const permission = { value: "unknown", basis: "not-reported" };
const summary = () => ({ previewId, revision: 1, predecessorRevision: null, attemptId: previewId, recordCount: 2,
  mappingId: previewId, mappingRevision: 1, mappingHighWater: 1, mappingMode: "automatic", delimiter: ",", undoTargetRevision: null,
  rights: Object.fromEntries(["store", "inspect", "index", "derive", "model-use", "quote", "export", "share"].map((name) => [name, { ...permission }])),
  options: { duplicatePolicy: "review", malformedPolicy: "exclude-and-report" } });
const page = () => ({ revision: 1, nextAfter: 2, complete: true, records: [{ ordinal: 2, recordKey: "a".repeat(64),
  kind: "record", status: "parsed", included: true, title: { text: "Synthetic", truncated: false }, doi: null, fieldCount: 1, warnings: [] }] });

const detail = () => ({ revision: 1, ordinal: 2, recordKey: "a".repeat(64), section: "raw", nextIndex: 1, complete: true,
  fields: [{ index: 0, name: "title", value: "Synthetic", sourceFieldIndex: 0, origin: "raw", target: null, warnings: [] }] });

describe("import review generated client", () => {
  const item = () => ({ previewId, state: "created", sourceName: "synthetic.csv", formatName: "csv", encoding: "utf-8", byteLength: 0, chunkCount: 0, jobId: null, jobState: null });
  it("bounds discovery and status without admitting paths, extra authority or unordered pages", () => {
    expect(decodeImportPreviewItem(item())).not.toBeNull();
    expect(decodeImportPreviewItem({ ...item(), sourceName: "../private.csv" })).toBeNull();
    expect(decodeImportPreviewItem({ ...item(), sessionId: "a".repeat(32) })).toBeNull();
    expect(decodeImportPreviewItem({ ...item(), jobState: "succeeded" })).toBeNull();
    expect(decodeImportPreviewPage({ items: [item()], nextAfter: previewId, complete: true })).not.toBeNull();
    expect(decodeImportPreviewPage({ items: [item(),item()], nextAfter: previewId, complete: false })).toBeNull();
    expect(decodeImportPreviewPage({ items: [], nextAfter: null, complete: false })).toBeNull();
  });
  it("binds discovery and status to owned inputs and rejects a cursor that fails to advance", async () => {
    let resolve!: (value: any) => void;
    const client = createCoreApiClient(async () => new Promise((done) => { resolve = done; }));
    const command = { ...address };
    const pending = client.importPreviewStatus(command);
    command.previewId = "01900000-0000-7000-8000-000000000002";
    resolve({ status: 200, contentType: "application/json", traceId: "a".repeat(32), etag: null, body: JSON.stringify({ ...item(), previewId: command.previewId }) });
    await expect(pending).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
    const page = client.importPreviews({ root: address.root, after: previewId, limit: 1 });
    resolve({ status: 200, contentType: "application/json", traceId: "a".repeat(32), etag: null, body: JSON.stringify({ items: [], nextAfter: previewId, complete: false }) });
    await expect(page).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
  });
  const changedPreview = "01900000-0000-7000-8000-000000000002";
  const mutationCases = [
    ["beginImportReview", { ...address }, "previewId", changedPreview, { ...summary(), previewId: changedPreview }],
    ["importReview", { ...address }, "previewId", changedPreview, { ...summary(), previewId: changedPreview }],
    ["importReviewPage", { ...address, revision: 1, after: 1, limit: 25 }, "revision", 2, { ...page(), revision: 2 }],
    ["importReviewDetail", { ...address, revision: 1, ordinal: 2, recordKey: "a".repeat(64), section: "raw", start: 0, limit: 25 }, "recordKey", "b".repeat(64), { ...detail(), recordKey: "b".repeat(64) }],
    ["mapImportReview", { ...address, expectedRevision: 1, mode: "columns", columns: [{ index: 0, target: "title" }] }, "expectedRevision", 2, { ...summary(), revision: 3, predecessorRevision: 2 }],
    ["editImportReview", { ...address, expectedRevision: 1, included: false, corrections: [], records: [{ ordinal: 2, recordKey: "a".repeat(64) }] }, "expectedRevision", 2, { ...summary(), revision: 3, predecessorRevision: 2 }],
    ["undoImportReview", { ...address, expectedRevision: 2 }, "expectedRevision", 3, { ...summary(), revision: 4, predecessorRevision: 3 }],
    ["importDiagnosticPage", { ...address, revision: 1, after: 0, limit: 25 }, "revision", 2, { revision: 2, nextAfter: 2, complete: true, csv: "ordinal,line_start,line_end,status,diagnostic\r\n1,1,1,parsed,none\r\n2,2,2,parsed,none\r\n" }],
  ] as const;

  it.each(mutationCases)("%s binds a delayed reply to the sent request snapshot", async (method, input, field, changed, response) => {
    const command = structuredClone(input) as any;
    let resolve!: (value: any) => void;
    let sent: any;
    const client = createCoreApiClient(async (request) => {
      sent = JSON.parse(request.body!);
      return new Promise((done) => { resolve = done; });
    });
    const pending = client[method](command);
    command[field] = changed;
    expect(sent[field]).not.toEqual(changed);
    resolve({ status: 200, contentType: "application/json", traceId: "a".repeat(32), etag: null, body: JSON.stringify(response) });
    await expect(pending).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
  });

  it("keeps a valid original reply valid after caller mutation", async () => {
    const command = { ...address, revision: 1, after: 1, limit: 25 };
    let resolve!: (value: any) => void;
    const client = createCoreApiClient(async () => new Promise((done) => { resolve = done; }));
    const pending = client.importReviewPage(command);
    command.revision = 2;
    resolve({ status: 200, contentType: "application/json", traceId: "a".repeat(32), etag: null, body: JSON.stringify(page()) });
    await expect(pending).resolves.toMatchObject({ revision: 1 });
  });
  it("owns bounded immutable values while retaining unknown action rights", () => {
    const value = summary();
    const result = decodeReviewSummary(value);
    expect(result?.rights.export.value).toBe("unknown");
    expect(Object.isFrozen(result?.rights.export)).toBe(true);
    value.rights.export!.value = "permitted";
    expect(result?.rights.export.value).toBe("unknown");
    expect(decodeReviewSummary({ ...summary(), mappingHighWater: 0 })).toBeNull();
    expect(decodeReviewSummary({ ...summary(), delimiter: "|" })).toBeNull();
    expect(decodeReviewSummary({ ...summary(), delimiter: ";" })?.delimiter).toBe(";");
    expect(decodeReviewSummary({ ...summary(), undoTargetRevision: 1 })).toBeNull();
    expect(decodeReviewSummary({ ...summary(), undoTargetRevision: true })).toBeNull();
    const granted = summary(); granted.rights.export!.value = "permitted";
    expect(decodeReviewSummary(granted)).toBeNull();
    let invoked = false;
    expect(decodeReviewSummary({ get previewId() { invoked = true; return previewId; } })).toBeNull();
    expect(invoked).toBe(false);
  });

  it("validates record order, details and complete report fragments", () => {
    expect(decodeReviewPage(page())).not.toBeNull();
    expect(decodeReviewPage({ ...page(), nextAfter: 1 })).toBeNull();
    expect(decodeReviewPage({ ...page(), records: [page().records[0], page().records[0]] })).toBeNull();
    expect(decodeReviewDetail({ revision: 1, ordinal: 2, recordKey: "a".repeat(64), section: "raw", nextIndex: 1, complete: true,
      fields: [{ index: 0, name: "title", value: "=untrusted", sourceFieldIndex: 0, origin: "raw", target: null, warnings: [] }] })).not.toBeNull();
    expect(decodeDiagnosticPage({ revision: 1, nextAfter: 2, complete: true, csv: "2,2,2,parsed,none\r\n" })).not.toBeNull();
  });

  it("serializes exact review requests and binds responses to their requested revision", async () => {
    const requests: unknown[] = [];
    const client = createCoreApiClient(async (request) => {
      requests.push(request);
      return { status: 200, contentType: "application/json", traceId: "a".repeat(32), etag: null,
        body: JSON.stringify(request.path.endsWith("/records") ? page() : summary()) };
    });
    await client.beginImportReview(address);
    await client.importReviewPage({ ...address, revision: 1, after: 1, limit: 25 });
    expect(requests).toHaveLength(2);
    expect(requests[1]).toMatchObject({ path: "/projects/imports/records", body: JSON.stringify({ ...address, revision: 1, after: 1, limit: 25 }) });
    await expect(client.importReviewPage({ ...address, revision: 2, after: 1, limit: 25 })).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
    await expect(client.importReviewPage({ ...address, revision: 1, after: 1, limit: 101 })).rejects.toThrow("RO-CORE-REQUEST-INVALID");
    expect(requests).toHaveLength(3);
  });
});
