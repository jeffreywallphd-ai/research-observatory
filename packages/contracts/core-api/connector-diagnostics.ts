import { CoreApiClientError, decodeConnectorRecentRuns, decodeProblemDetail, type ConnectorDiagnostics, type ConnectorDiagnosticsRequest, type CoreApiTransport } from "./generated";

const LIMIT = 65536;
const ERROR_CODES = ["authentication", "permission-denied", "rate-limit", "provider-unavailable", "timeout", "invalid-query", "incompatible-response", "policy-denied", "cancelled", "not-configured", "unsupported-operation", "invalid-cursor", "partial-response", "response-too-large"];
type JsonObject = Readonly<Record<string, unknown>>;
const record = (value: unknown): JsonObject | null => value !== null && typeof value === "object" && !Array.isArray(value) ? value as JsonObject : null;
const keys = (value: JsonObject, names: readonly string[]): boolean => Object.keys(value).length === names.length && names.every(name => Object.hasOwn(value, name));
const integer = (value: unknown, min = 0, max = Number.MAX_SAFE_INTEGER): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= min && value <= max;
const member = (value: unknown, values: readonly string[]): value is string => typeof value === "string" && values.includes(value);
const uuid = (value: unknown): value is string => typeof value === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(value);
function instant(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value)) return false;
  const time = Date.parse(value);
  return Number.isFinite(time) && new Date(time).toISOString() === value;
}

// Own bounded plain JSON without invoking caller accessors or toJSON methods.
function owned(value: unknown): JsonObject | null {
  let nodes = 0;
  const seen = new Set<object>();
  function copy(item: unknown, depth: number): unknown {
    if (++nodes > 512 || depth > 10) throw new Error("bounded-json");
    if (item === null || typeof item === "boolean") return item;
    if (typeof item === "number" && Number.isFinite(item)) return item;
    if (typeof item === "string" && item.length <= LIMIT) return item;
    if (typeof item !== "object" || item === null || seen.has(item)) throw new Error("plain-json");
    const array = Array.isArray(item);
    if (!array && ![Object.prototype, null].includes(Object.getPrototypeOf(item))) throw new Error("plain-json");
    seen.add(item);
    const descriptors = Object.getOwnPropertyDescriptors(item);
    if (Reflect.ownKeys(item).some(key => typeof key !== "string")) throw new Error("plain-json");
    if (array) {
      if (item.length > 64 || Object.keys(descriptors).length !== item.length + 1) throw new Error("bounded-array");
      return Array.from({ length: item.length }, (_, index) => {
        const property = descriptors[String(index)];
        if (!property || !("value" in property) || !property.enumerable) throw new Error("plain-json");
        return copy(property.value, depth + 1);
      });
    }
    const result: Record<string, unknown> = Object.create(null);
    for (const [name, property] of Object.entries(descriptors)) {
      if (!("value" in property) || !property.enumerable || ["__proto__", "constructor", "prototype"].includes(name)) throw new Error("plain-json");
      result[name] = copy(property.value, depth + 1);
    }
    return result;
  }
  try {
    const result = record(copy(value, 0));
    return result && new TextEncoder().encode(JSON.stringify(result)).length <= LIMIT ? result : null;
  } catch { return null; }
}

function measurements(value: unknown): boolean {
  const item = record(value);
  return !!item && keys(item, ["httpRequests", "httpRetries", "exchangeElapsedMs", "brokerElapsedMs", "lastHttpStatus", "scope"])
    && integer(item.httpRequests, 0, 3) && integer(item.httpRetries, 0, 2)
    && item.httpRetries === Math.max(0, item.httpRequests - 1) && integer(item.brokerElapsedMs)
    && (item.httpRequests === 0 ? item.exchangeElapsedMs === null && item.lastHttpStatus === null
      : integer(item.exchangeElapsedMs) && item.exchangeElapsedMs <= item.brokerElapsedMs + 1 && (item.lastHttpStatus === null || integer(item.lastHttpStatus, 100, 999)))
    && item.scope === "transport-attempts-and-broker-before-publication";
}

export function decodeConnectorDiagnostics(value: unknown): ConnectorDiagnostics | null {
  const item = owned(value);
  if (!item || !keys(item, ["job", "observation"])) return null;
  const recent = decodeConnectorRecentRuns({ items: [item.job], scope: "latest-20-source-jobs-within-100-workflows" });
  const job = recent?.items[0];
  if (!job || !instant(job.updatedAt)) return null;
  if (item.observation === null) return item as unknown as ConnectorDiagnostics;
  const page = record(item.observation);
  if (!page || !keys(page, ["observationId", "observedAt", "outcome", "continuation", "pageIndex", "nextPageIndex", "measurements", "responseBodyState", "responseByteLength", "cacheState", "cacheAgeMs", "rate", "errors", "warnings"])
    || !uuid(page.observationId) || page.observationId === job.invocationId || !instant(page.observedAt)
    || !member(page.outcome, ["complete", "partial", "failed"])
    || !member(page.continuation, ["exhausted", "next-page", "retry-current", "unavailable"])
    || !integer(page.pageIndex, 0, 1000000)
    || (page.continuation === "next-page" ? !integer(page.nextPageIndex, 1, 1000000) || page.nextPageIndex !== page.pageIndex + 1 : page.nextPageIndex !== null)
    || (page.measurements !== null && !measurements(page.measurements))
    || !member(page.responseBodyState, ["retained", "permitted-fields-only", "unavailable"])
    || (page.responseByteLength !== null && !integer(page.responseByteLength, 0, 10485760))
    || (page.responseBodyState === "retained" && page.responseByteLength === null)
    || !member(page.cacheState, ["disabled", "miss", "hit", "revalidated", "not-permitted"])
    || (["hit", "revalidated"].includes(page.cacheState) ? !integer(page.cacheAgeMs) : page.cacheAgeMs !== null)
    || (page.cacheState === "hit" && page.measurements !== null && record(page.measurements)?.httpRequests !== 0)
    || !Array.isArray(page.errors) || page.errors.length > 16
    || !Array.isArray(page.warnings) || page.warnings.length > 32
    || !page.warnings.every(warning => typeof warning === "string" && /^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$/.test(warning) && warning.length <= 128)) return null;
  if (page.outcome === "complete" ? page.errors.length !== 0 || !["exhausted", "next-page"].includes(page.continuation)
    : page.errors.length === 0 || !["retry-current", "unavailable"].includes(page.continuation)) return null;
  for (const value of page.errors) {
    const error = record(value);
    if (!error || !keys(error, ["code", "retryable", "retryAfterMs"]) || !member(error.code, ERROR_CODES)
      || typeof error.retryable !== "boolean" || (error.retryable && !["rate-limit", "provider-unavailable", "timeout"].includes(error.code))
      || (error.retryAfterMs !== null && (!integer(error.retryAfterMs, 0, 300000) || !["rate-limit", "provider-unavailable"].includes(error.code)))) return null;
  }
  const rate = record(page.rate);
  if (!rate || !keys(rate, ["providerId", "observedAt", "remaining", "retryAfterMs", "circuit"])
    || rate.providerId !== job.providerId || !instant(rate.observedAt) || rate.observedAt > page.observedAt
    || (rate.remaining !== null && !integer(rate.remaining))
    || (rate.retryAfterMs !== null && !integer(rate.retryAfterMs, 0, 300000))
    || !member(rate.circuit, ["closed", "open", "half-open", "unknown"])) return null;
  return item as unknown as ConnectorDiagnostics;
}

export function createConnectorDiagnosticsClient(transport: CoreApiTransport) {
  return Object.freeze({
    async inspect(command: ConnectorDiagnosticsRequest): Promise<ConnectorDiagnostics | null> {
      const request = owned(command);
      const root = request?.root;
      const normalized = typeof root === "string" ? root.replaceAll("\\", "/") : "";
      if (!request || !keys(request, ["root", "previewId"]) || typeof root !== "string" || root.length > 4096
        || /[\u0000-\u001f\u007f]/.test(root) || !/^(?:[A-Za-z]:\/|\/\/[^/]+\/[^/]+\/|\/)/.test(normalized)
        || normalized.split("/").includes("..") || !uuid(request.previewId)) throw new Error("RO-CORE-REQUEST-INVALID");
      const response = await transport({ method: "POST", path: "/projects/connectors/diagnostics", body: JSON.stringify({ root, previewId: request.previewId }), ifMatch: null, idempotencyKey: null });
      if (!integer(response.status, 100, 599) || typeof response.traceId !== "string" || !/^[0-9a-f]{32}$/.test(response.traceId)
        || typeof response.body !== "string" || response.body.length > LIMIT) throw new Error("RO-CORE-RESPONSE-INVALID");
      let body: unknown;
      try { body = JSON.parse(response.body); } catch { throw new Error("RO-CORE-RESPONSE-INVALID"); }
      if (response.status >= 400) {
        const problem = decodeProblemDetail(body);
        if (response.contentType !== "application/problem+json" || !problem || problem.status !== response.status || problem.traceId !== response.traceId) throw new Error("RO-CORE-RESPONSE-INVALID");
        throw new CoreApiClientError(problem);
      }
      if (response.status !== 200 || response.contentType !== "application/json") throw new Error("RO-CORE-RESPONSE-INVALID");
      if (body === null) return null;
      const result = decodeConnectorDiagnostics(body);
      if (!result || result.job.previewId !== request.previewId) throw new Error("RO-CORE-RESPONSE-INVALID");
      return result;
    },
  });
}
