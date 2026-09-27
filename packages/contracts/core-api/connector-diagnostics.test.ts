import { describe, expect, it, vi } from "vitest";
import type { CoreApiResponse } from "./generated";
import { createConnectorDiagnosticsClient, decodeConnectorDiagnostics } from "./connector-diagnostics";

const id = "01900000-0000-7000-8000-000000000001";
const observationId = "01900000-0000-7000-8000-000000000002";
const root = "C:/Research/synthetic";
function diagnostic() {
  return {
    job: { previewId: id, invocationId: id, jobId: id, workflowRunId: id, providerId: "unpaywall", operation: "oa-resolution", state: "succeeded", updatedAt: "2026-09-24T12:00:00.000Z", diagnosticCode: null },
    observation: {
      observationId, observedAt: "2026-09-24T12:00:00.000Z", outcome: "complete", continuation: "exhausted", pageIndex: 0, nextPageIndex: null,
      measurements: { httpRequests: 1, httpRetries: 0, exchangeElapsedMs: 125, brokerElapsedMs: 130, lastHttpStatus: 200, scope: "transport-attempts-and-broker-before-publication" },
      responseBodyState: "retained", responseByteLength: 230, cacheState: "disabled", cacheAgeMs: null,
      rate: { providerId: "unpaywall", observedAt: "2026-09-24T12:00:00.000Z", remaining: null, retryAfterMs: null, circuit: "closed" }, errors: [], warnings: [],
    },
  };
}
const response = (body: unknown): CoreApiResponse => ({ status: 200, contentType: "application/json", traceId: "a".repeat(32), etag: null, body: JSON.stringify(body) });

describe("protected source diagnostics", () => {
  it("owns a strict content-free projection and retains historical unknown measurements", () => {
    const raw = diagnostic();
    const decoded = decodeConnectorDiagnostics(raw);
    expect(decoded).toEqual(raw);
    raw.observation.measurements.httpRequests = 3;
    expect(decoded?.observation?.measurements?.httpRequests).toBe(1);
    expect(decodeConnectorDiagnostics({ ...diagnostic(), observation: null })).not.toBeNull();
    const historical = diagnostic();
    expect(decodeConnectorDiagnostics({ ...historical, observation: { ...historical.observation, measurements: null } })).not.toBeNull();
  });
  it("distinguishes cache-only zero attempts from unavailable historical measurements", () => {
    const value = diagnostic();
    value.observation.cacheState = "hit";
    expect(decodeConnectorDiagnostics(value)).toBeNull();
    expect(decodeConnectorDiagnostics({ ...value, observation: { ...value.observation, cacheAgeMs: 100,
      measurements: { ...value.observation.measurements, httpRequests: 0, httpRetries: 0, exchangeElapsedMs: null, lastHttpStatus: null },
    } })).not.toBeNull();
  });
  it("rejects inconsistent counts, durations, status and authority-bearing extras", () => {
    for (const delta of [{ httpRequests: true }, { httpRequests: 4 }, { httpRetries: 1 }, { httpRequests: 0 },
      { exchangeElapsedMs: null }, { exchangeElapsedMs: -1 }, { brokerElapsedMs: NaN }, { brokerElapsedMs: Infinity },
      { brokerElapsedMs: 1.5 }, { brokerElapsedMs: 1 }, { lastHttpStatus: 1000 }, { key: "synthetic" }]) {
      const value = diagnostic();
      expect(decodeConnectorDiagnostics({ ...value, observation: { ...value.observation, measurements: { ...value.observation.measurements, ...delta } } })).toBeNull();
    }
    for (const delta of [{ queryJson: "private" }, { records: [] }, { observationId: id }, { observedAt: "2026-02-30T12:00:00Z" },
      { pageIndex: -1 }, { nextPageIndex: 1 }, { cacheAgeMs: 1 }, { responseByteLength: 10485761 }, { errors: [{ code: "new-unbounded-error", retryable: false, retryAfterMs: null }] }]) {
      const value = diagnostic();
      expect(decodeConnectorDiagnostics({ ...value, observation: { ...value.observation, ...delta } })).toBeNull();
    }
    const value = diagnostic();
    expect(decodeConnectorDiagnostics({ ...value, observation: { ...value.observation, rate: { ...value.observation.rate, providerId: "crossref" } } })).toBeNull();
    expect(decodeConnectorDiagnostics({ ...value, permission: "inspect" })).toBeNull();
    let accessed = false;
    expect(decodeConnectorDiagnostics({ get job() { accessed = true; return value.job; }, observation: value.observation })).toBeNull();
    expect(accessed).toBe(false);
  });
  it("reads only the exact preview and rejects substituted identities or response envelopes", async () => {
    const transport = vi.fn(async () => response(diagnostic()));
    await expect(createConnectorDiagnosticsClient(transport).inspect({ root, previewId: id })).resolves.toEqual(diagnostic());
    expect(transport).toHaveBeenCalledWith({ method: "POST", path: "/projects/connectors/diagnostics", body: JSON.stringify({ root, previewId: id }), ifMatch: null, idempotencyKey: null });
    await expect(createConnectorDiagnosticsClient(async () => response(null)).inspect({ root, previewId: id })).resolves.toBeNull();
    const foreign = diagnostic(); foreign.job.previewId = observationId;
    for (const invalid of [response(foreign), { ...response(diagnostic()), status: 201 },
      { ...response(diagnostic()), traceId: "invalid" }, { ...response(diagnostic()), contentType: "text/html" },
      { ...response(diagnostic()), body: "{" }, { ...response(diagnostic()), body: " ".repeat(65537) }]) {
      await expect(createConnectorDiagnosticsClient(async () => invalid).inspect({ root, previewId: id })).rejects.toThrow("RO-CORE-RESPONSE-INVALID");
    }
    await expect(createConnectorDiagnosticsClient(transport).inspect({ root: "relative", previewId: id })).rejects.toThrow("RO-CORE-REQUEST-INVALID");
    await expect(createConnectorDiagnosticsClient(transport).inspect({ root, previewId: "invalid" })).rejects.toThrow("RO-CORE-REQUEST-INVALID");
    expect(transport).toHaveBeenCalledTimes(1);
  });
});
