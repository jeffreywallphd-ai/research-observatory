import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { createCoreApiClient, decodeModelCatalogProjection, type ModelCatalogProjection, type ModelManifest } from "./generated";

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(
    ([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`,
  ).join(",")}}`;
  return JSON.stringify(value);
}

export function modelCatalogFixture(): ModelCatalogProjection {
  const task = JSON.parse(readFileSync(new URL("../model-gateway/fixtures/valid-generation-task.v1.json", import.meta.url), "utf8"));
  const { mode: _mode, ...identity } = task.execution;
  const manifest: ModelManifest = {
    schemaVersion: "1.0", manifestId: "fixture-scholar", revision: 1, identity,
    deployment: "local", licenseId: "fixture-license", capabilities: ["generation"], features: ["structured-output"],
    modalities: ["text"], contextTokens: 8192, maxOutputTokens: 1024, supportsCitations: true,
    platforms: ["windows-x64"], minimumMemoryMiB: 2048, accelerator: "none", qualityTier: "balanced",
    allowedDataClasses: ["confidential", "internal", "public"], costMicrounitsPerThousandTokens: 0,
    declaredAvailability: "available", retired: false,
  };
  const projectId = "123e4567-e89b-42d3-a456-426614174000";
  const catalogHash = `sha256:${"a".repeat(64)}`;
  return {
    schemaVersion: "1.0", projectId, revision: 1, latestRevision: 1, catalogHash, modelCount: 1,
    inventoryState: "available", executionAvailable: false,
    entries: [{ manifest, manifestHash: `sha256:${createHash("sha256").update(canonical(manifest)).digest("hex")}`,
      availability: "ready", qualifiedTaskKinds: ["generation"], reasonCodes: ["task-policy-check-required"], eligibility: "not-evaluated" }],
    nextManifestId: null, nextHistoryRevision: null,
    history: [{ revision: 1, catalogHash, recordHash: `sha256:${"b".repeat(64)}`, previousHash: null,
      occurredAt: "2026-09-06T12:00:00.000Z", modelCount: 1 }],
  };
}

describe("model registry client boundary", () => {
  it("owns a deeply immutable projection and does not turn availability into permission", () => {
    const fixture = modelCatalogFixture();
    const decoded = decodeModelCatalogProjection(fixture);
    expect(decoded).not.toBeNull();
    expect(decoded?.executionAvailable).toBe(false);
    expect(Object.isFrozen(decoded?.entries[0]?.manifest.features)).toBe(true);
    (fixture.entries[0]!.manifest.features as string[]).push("changed-after-decode");
    expect(decoded?.entries[0]?.manifest.features).toEqual(["structured-output"]);
  });

  it("rejects malformed, contradictory, substituted and spoofed projections", () => {
    const mutations: ((value: any) => void)[] = [
      (x) => { x.allowed = true; }, (x) => { x.executionAvailable = true; },
      (x) => { x.entries[0].availability = { ready: true }; },
      (x) => { x.entries[0].manifest.allowed = true; },
      (x) => { x.entries[0].manifest.contextTokens = "8192"; },
      (x) => { x.entries[0].manifestHash = `sha256:${"0".repeat(64)}`; },
      (x) => { x.entries[0].availability = "stale"; },
      (x) => { x.entries[0].qualifiedTaskKinds = ["embedding"]; },
      (x) => { x.entries[0].reasonCodes = []; },
      (x) => { x.history[0].catalogHash = `sha256:${"0".repeat(64)}`; },
      (x) => { x.latestRevision = 0; }, (x) => { x.nextManifestId = "not-the-last-entry"; },
      (x) => { x.entries[0].manifest.revision = Number.NaN; },
    ];
    for (const mutate of mutations) {
      const candidate = modelCatalogFixture(); mutate(candidate);
      expect(decodeModelCatalogProjection(candidate)).toBeNull();
    }
    let invoked = false;
    const hostile = { get entries() { invoked = true; return []; } };
    expect(decodeModelCatalogProjection(hostile)).toBeNull();
    expect(invoked).toBe(false);
  });

  it("serializes only the read/refresh authority fields and requires an idempotency identity", async () => {
    const requests: unknown[] = [];
    const client = createCoreApiClient(async (request) => {
      requests.push(request);
      return { status: 200, contentType: "application/json", traceId: "a".repeat(32), etag: null,
        body: JSON.stringify(modelCatalogFixture()) };
    });
    await client.modelCatalog({ root: "C:/Research/fixture", revision: null, afterManifestId: null, beforeHistoryRevision: null });
    await client.refreshModelCatalog({ root: "C:/Research/fixture", expectedRevision: 0 }, "b".repeat(32));
    expect(requests).toHaveLength(2);
    expect(requests[1]).toMatchObject({ path: "/projects/models/refresh", idempotencyKey: "b".repeat(32),
      body: JSON.stringify({ root: "C:/Research/fixture", expectedRevision: 0 }) });
    await expect(client.refreshModelCatalog({ root: "C:/Research/fixture", expectedRevision: 0 }, "")).rejects.toThrow();
    expect(requests).toHaveLength(2);
  });
});
