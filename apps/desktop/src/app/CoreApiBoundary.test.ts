import { describe, expect, it } from "vitest";

import { decodeNativeCoreApiResponse, verifyPackagedCoreApiCompatibility } from "./CoreApiBoundary";

const traceId = "0123456789abcdef0123456789abcdef";

describe("native Core API boundary", () => {
  it("decodes only the exact secret-free native response envelope", () => {
    const valid = {
      status: 200,
      contentType: "application/json",
      traceId,
      etag: null,
      body: "{}",
    };
    expect(decodeNativeCoreApiResponse(valid)).toEqual(valid);
    expect(decodeNativeCoreApiResponse({ ...valid, authorization: "Bearer secret" })).toBeNull();
    expect(decodeNativeCoreApiResponse({ ...valid, traceId: "../private" })).toBeNull();
    expect(decodeNativeCoreApiResponse(new Proxy({}, { ownKeys: () => { throw new Error("private"); } }))).toBeNull();
  });

  it("uses the generated client to accept matching and reject incompatible Core versions", async () => {
    const base = {
      schemaVersion: "1.0",
      service: "research-observatory-core",
      version: "0.1.0",
      apiVersion: "1.0.0",
      minimumClientApiVersion: "1.0.0",
      maximumClientApiVersionExclusive: "2.0.0",
    };
    const transport = async () => ({
      status: 200,
      contentType: "application/json",
      traceId,
      etag: null,
      body: JSON.stringify(base),
    });
    await expect(verifyPackagedCoreApiCompatibility(transport)).resolves.toMatchObject({ ok: true });
    await expect(verifyPackagedCoreApiCompatibility(async () => ({
      ...(await transport()),
      body: JSON.stringify({ ...base, apiVersion: "2.0.0" }),
    }))).resolves.toMatchObject({ ok: false, code: "RO-CORE-API-INCOMPATIBLE" });
  });
});
