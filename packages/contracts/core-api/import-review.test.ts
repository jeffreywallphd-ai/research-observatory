import { describe, expect, it } from "vitest";
import { createCoreApiClient, decodeReviewSummary, decodeReviewPage, decodeReviewDetail, decodeDiagnosticPage } from "./generated";

const previewId = "01900000-0000-7000-8000-000000000001";
const address = { root: "C:/Research/synthetic", previewId };
const permission = { value: "unknown", basis: "not-reported" };
const summary = () => ({ previewId, revision: 1, predecessorRevision: null, attemptId: previewId, recordCount: 2,
  mappingId: previewId, mappingRevision: 1, mappingHighWater: 1, mappingMode: "automatic",
  rights: Object.fromEntries(["store", "inspect", "index", "derive", "model-use", "quote", "export", "share"].map((name) => [name, { ...permission }])),
  options: { duplicatePolicy: "review", malformedPolicy: "exclude-and-report" } });
const page = () => ({ revision: 1, nextAfter: 2, complete: true, records: [{ ordinal: 2, recordKey: "a".repeat(64),
  kind: "record", status: "parsed", included: true, title: { text: "Synthetic", truncated: false }, doi: null, fieldCount: 1, warnings: [] }] });

describe("import review generated client", () => {
  it("owns bounded immutable values while retaining unknown action rights", () => {
    const value = summary();
    const result = decodeReviewSummary(value);
    expect(result?.rights.export.value).toBe("unknown");
    expect(Object.isFrozen(result?.rights.export)).toBe(true);
    value.rights.export!.value = "permitted";
    expect(result?.rights.export.value).toBe("unknown");
    expect(decodeReviewSummary({ ...summary(), mappingHighWater: 0 })).toBeNull();
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
