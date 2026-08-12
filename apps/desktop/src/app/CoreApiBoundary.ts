import { invoke } from "@tauri-apps/api/core";

import {
  createCoreApiClient,
  evaluateCoreApiCompatibility,
  type CompatibilityResult,
  type CoreApiRequest,
  type CoreApiResponse,
  type CoreApiTransport,
} from "@research-observatory/contracts/core-api";

function hasExactKeys(value: Readonly<Record<string, unknown>>, keys: readonly string[]): boolean {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
}

export function decodeNativeCoreApiResponse(value: unknown): CoreApiResponse | null {
  try {
    if (value === null || typeof value !== "object" || Array.isArray(value)) return null;
    const candidate = value as Readonly<Record<string, unknown>>;
    if (!hasExactKeys(candidate, ["status", "contentType", "traceId", "etag", "body"])) return null;
    if (typeof candidate.status !== "number" || !Number.isInteger(candidate.status) || candidate.status < 100 || candidate.status > 599) return null;
    if (candidate.contentType !== "application/json" && candidate.contentType !== "application/problem+json" && candidate.contentType !== "text/event-stream") return null;
    if (typeof candidate.traceId !== "string" || !/^[0-9a-f]{32}$/.test(candidate.traceId)) return null;
    if (candidate.etag !== null && (typeof candidate.etag !== "string" || candidate.etag.length > 160)) return null;
    if (typeof candidate.body !== "string" || candidate.body.length > 1_048_576) return null;
    return candidate as unknown as CoreApiResponse;
  } catch {
    return null;
  }
}

export const packagedCoreApiTransport: CoreApiTransport = async (request: CoreApiRequest) => {
  const result = await invoke<unknown>("core_api_request", { request });
  const decoded = decodeNativeCoreApiResponse(result);
  if (!decoded) throw new Error("RO-CORE-API-RESPONSE-INVALID");
  return decoded;
};

export async function verifyPackagedCoreApiCompatibility(
  transport: CoreApiTransport = packagedCoreApiTransport,
): Promise<CompatibilityResult> {
  const version = await createCoreApiClient(transport).version();
  return evaluateCoreApiCompatibility(version);
}
