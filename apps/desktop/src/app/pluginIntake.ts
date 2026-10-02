import { invoke } from "@tauri-apps/api/core";

export interface PluginDestination {
  readonly scheme: "https";
  readonly host: string;
  readonly port: number;
  readonly pathTemplate: string;
}

export interface PluginPackageReview {
  readonly pluginId: string;
  readonly pluginVersion: string;
  readonly publisherKeyId: string;
  readonly sourceDisplayName: string;
  readonly manifestSha256: string;
  readonly packageSha256: string;
  readonly signatureSha256: string;
  readonly permissions: readonly string[];
  readonly destinations: readonly PluginDestination[];
  readonly operations: readonly string[];
  readonly dataClasses: readonly string[];
  readonly credentialScopes: readonly string[];
  readonly resourceProfile: { readonly committedMemoryMiB: number; readonly maxJobsPerProject: number; readonly wallTimeSeconds: number };
  readonly trustStatus: string;
  readonly grantStatus: string;
  readonly runtimeStatus: "ready" | "unavailable";
}

export interface ReviewedPluginPackage {
  readonly packageToken: string;
  readonly expiresAt: string;
  readonly review: PluginPackageReview;
}

export type PluginIntakeOutcome = { readonly status: "reviewed"; readonly package: ReviewedPluginPackage }
  | { readonly status: "cancelled" | "unavailable" | "failed" };

export type PluginNativeTransport = (command: string, arguments_?: Record<string, unknown>) => Promise<unknown>;
const native: PluginNativeTransport = (command, arguments_) => invoke(command, arguments_);
const sha = /^sha256:[0-9a-f]{64}$/;
const token = /^[0-9a-f]{64}$/;
const id = /^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$/;
const version = /^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$/;

function object(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  if (Reflect.ownKeys(value).some((key) => typeof key !== "string" || !("value" in descriptors[key]!))) return null;
  return Object.fromEntries(Object.entries(descriptors).map(([key, descriptor]) => [key, descriptor.value]));
}
function keys(value: Record<string, unknown>, expected: readonly string[]): boolean {
  return Object.keys(value).length === expected.length && expected.every((key) => Object.hasOwn(value, key));
}
function strings(value: unknown, maximum: number): string[] | null {
  return Array.isArray(value) && value.length <= maximum && value.every((item) => typeof item === "string" && item.length > 0 && item.length <= 256)
    && new Set(value).size === value.length ? [...value] : null;
}
function decodeReview(value: unknown): PluginPackageReview | null {
  const review = object(value);
  if (!review || !keys(review, ["pluginId", "pluginVersion", "publisherKeyId", "sourceDisplayName", "manifestSha256", "packageSha256", "signatureSha256", "permissions", "destinations", "operations", "dataClasses", "credentialScopes", "resourceProfile", "trustStatus", "grantStatus", "runtimeStatus"])) return null;
  if (typeof review.pluginId !== "string" || review.pluginId.length > 121 || !id.test(review.pluginId)
    || typeof review.pluginVersion !== "string" || !version.test(review.pluginVersion)
    || typeof review.publisherKeyId !== "string" || review.publisherKeyId.length > 128 || !/^[A-Za-z0-9][A-Za-z0-9._:-]*$/.test(review.publisherKeyId)
    || typeof review.sourceDisplayName !== "string" || !review.sourceDisplayName.trim() || review.sourceDisplayName.length > 128
    || typeof review.manifestSha256 !== "string" || !sha.test(review.manifestSha256)
    || typeof review.packageSha256 !== "string" || !sha.test(review.packageSha256)
    || typeof review.signatureSha256 !== "string" || !sha.test(review.signatureSha256)
    || typeof review.trustStatus !== "string" || !["untrusted", "active", "revoked", "invalid"].includes(review.trustStatus)
    || typeof review.grantStatus !== "string" || !["disabled", "enabled", "different-package"].includes(review.grantStatus)
    || (review.runtimeStatus !== "ready" && review.runtimeStatus !== "unavailable")) return null;
  const permissions = strings(review.permissions, 2); const operations = strings(review.operations, 6);
  const dataClasses = strings(review.dataClasses, 4); const credentialScopes = strings(review.credentialScopes, 16);
  if (!permissions || !operations || !dataClasses || !credentialScopes || !Array.isArray(review.destinations) || review.destinations.length > 16) return null;
  const destinations: PluginDestination[] = [];
  for (const value of review.destinations) {
    const destination = object(value);
    if (!destination || !keys(destination, ["scheme", "host", "port", "pathTemplate"])
      || destination.scheme !== "https" || typeof destination.host !== "string" || destination.host.length > 253 || !/^[a-z0-9.-]+$/.test(destination.host)
      || typeof destination.port !== "number" || !Number.isInteger(destination.port) || destination.port < 1 || destination.port > 65535
      || typeof destination.pathTemplate !== "string" || destination.pathTemplate.length > 256 || !destination.pathTemplate.startsWith("/")) return null;
    destinations.push(destination as unknown as PluginDestination);
  }
  const resource = object(review.resourceProfile);
  if (!resource || !keys(resource, ["committedMemoryMiB", "maxJobsPerProject", "wallTimeSeconds"])
    || typeof resource.committedMemoryMiB !== "number" || !Number.isInteger(resource.committedMemoryMiB) || resource.committedMemoryMiB < 16 || resource.committedMemoryMiB > 256
    || resource.maxJobsPerProject !== 1 || typeof resource.wallTimeSeconds !== "number" || !Number.isInteger(resource.wallTimeSeconds) || resource.wallTimeSeconds < 1 || resource.wallTimeSeconds > 60) return null;
  return { pluginId: review.pluginId, pluginVersion: review.pluginVersion, publisherKeyId: review.publisherKeyId,
    sourceDisplayName: review.sourceDisplayName, manifestSha256: review.manifestSha256, packageSha256: review.packageSha256,
    signatureSha256: review.signatureSha256, permissions, destinations, operations, dataClasses, credentialScopes,
    resourceProfile: resource as unknown as PluginPackageReview["resourceProfile"], trustStatus: review.trustStatus, grantStatus: review.grantStatus,
    runtimeStatus: review.runtimeStatus };
}

export function decodePluginIntakeOutcome(value: unknown): PluginIntakeOutcome | null {
  const result = object(value);
  if (!result) return null;
  if (keys(result, ["status"]) && ["cancelled", "unavailable", "failed"].includes(String(result.status))) return { status: result.status as "cancelled" | "unavailable" | "failed" };
  if (!keys(result, ["status", "packageToken", "expiresAt", "review"]) || result.status !== "reviewed"
    || typeof result.packageToken !== "string" || !token.test(result.packageToken)
    || typeof result.expiresAt !== "string" || Number.isNaN(Date.parse(result.expiresAt))) return null;
  const review = decodeReview(result.review);
  return review ? { status: "reviewed", package: { packageToken: result.packageToken, expiresAt: result.expiresAt, review } } : null;
}

export function decodePluginCandidateReview(value: unknown): ReviewedPluginPackage | null {
  const result = object(value);
  if (!result || !keys(result, ["packageToken", "expiresAt", "review"])
    || typeof result.packageToken !== "string" || !token.test(result.packageToken)
    || typeof result.expiresAt !== "string" || Number.isNaN(Date.parse(result.expiresAt))) return null;
  const review = decodeReview(result.review);
  return review ? { packageToken: result.packageToken, expiresAt: result.expiresAt, review } : null;
}

let selecting = false;
export async function choosePluginPackage(
  project: { readonly root: string; readonly projectId: string }, signal?: AbortSignal, transport: PluginNativeTransport = native,
): Promise<PluginIntakeOutcome> {
  if (signal?.aborted) return { status: "cancelled" };
  if (selecting) return { status: "unavailable" };
  const bytes = new Uint8Array(16); globalThis.crypto.getRandomValues(bytes);
  const operationId = Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
  const cancel = (): void => { void transport("cancel_connector_package_selection", { operationId }).catch(() => undefined); };
  selecting = true; signal?.addEventListener("abort", cancel, { once: true });
  try {
    const outcome = decodePluginIntakeOutcome(await transport("select_connector_package", { request: { root: project.root, projectId: project.projectId, operationId } }));
    if (signal?.aborted) {
      if (outcome?.status === "reviewed") {
        try { await transport("connector_plugin_action", { request: { root: project.root, projectId: project.projectId, kind: "discard", packageToken: outcome.package.packageToken } }); }
        catch { /* Core also expires the short-lived candidate on session close or TTL. */ }
      }
      return { status: "cancelled" };
    }
    return outcome ?? { status: signal?.aborted ? "cancelled" : "failed" };
  } catch { return { status: signal?.aborted ? "cancelled" : "failed" }; }
  finally { signal?.removeEventListener("abort", cancel); selecting = false; }
}
