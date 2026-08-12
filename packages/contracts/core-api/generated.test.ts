import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  CORE_API_OPENAPI_SHA256,
  CoreApiClientError,
  createCoreApiClient,
  decodeProblemDetail,
  decodeVersionResponse,
  evaluateCoreApiCompatibility,
  parseOperationEventStream,
  type CoreApiResponse,
  type VersionResponse,
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
});
