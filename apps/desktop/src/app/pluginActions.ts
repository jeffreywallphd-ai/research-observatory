import { invoke } from "@tauri-apps/api/core";
import { decodePluginCandidateReview, type PluginDestination, type PluginNativeTransport, type ReviewedPluginPackage } from "./pluginIntake";

export interface PluginTrustState {
  readonly publisherKeyId: string;
  readonly status: "untrusted" | "active" | "revoked";
  readonly revision: number | null;
  readonly publicKeySha256: string | null;
}

export interface PluginGrantState {
  readonly pluginId: string;
  readonly status: "disabled" | "enabled";
  readonly revision: number | null;
  readonly packageSha256: string | null;
  readonly manifestSha256: string | null;
  readonly permissions: readonly string[];
  readonly destinations: readonly PluginDestination[];
}

export type NativePluginResult = { readonly status: "ok"; readonly value: unknown }
  | { readonly status: "cancelled" | "unavailable" | "failed" };
const native: PluginNativeTransport = (command, arguments_) => invoke(command, arguments_);
const sha = /^sha256:[0-9a-f]{64}$/;
const id = /^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*$/;

function object(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  if (Reflect.ownKeys(value).some((key) => typeof key !== "string" || !("value" in descriptors[key]!))) return null;
  return Object.fromEntries(Object.entries(descriptors).map(([key, descriptor]) => [key, descriptor.value]));
}
function keys(value: Record<string, unknown>, expected: readonly string[]): boolean {
  return Object.keys(value).length === expected.length && expected.every((key) => Object.hasOwn(value, key));
}
function decodeOutcome(value: unknown): NativePluginResult {
  const result = object(value);
  if (result && keys(result, ["status", "value"]) && result.status === "ok") return { status: "ok", value: result.value };
  if (result && keys(result, ["status"]) && (result.status === "cancelled" || result.status === "unavailable" || result.status === "failed")) return { status: result.status };
  return { status: "failed" };
}
function digest(value: unknown): value is string { return typeof value === "string" && sha.test(value); }
function destinations(value: unknown): value is PluginDestination[] {
  if (!Array.isArray(value) || value.length > 16) return false;
  return value.every((item) => {
    const parsed = object(item);
    return parsed && keys(parsed, ["scheme", "host", "port", "pathTemplate"]) && parsed.scheme === "https"
      && typeof parsed.host === "string" && parsed.host.length > 0 && parsed.host.length <= 253
      && typeof parsed.port === "number" && Number.isInteger(parsed.port) && parsed.port > 0 && parsed.port <= 65535
      && typeof parsed.pathTemplate === "string" && parsed.pathTemplate.startsWith("/") && parsed.pathTemplate.length <= 256;
  });
}
export function decodeTrustState(value: unknown): PluginTrustState | null {
  const result = object(value);
  if (!result || !keys(result, ["publisherKeyId", "status", "revision", "publicKeySha256"])
    || typeof result.publisherKeyId !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(result.publisherKeyId)
    || (result.status !== "untrusted" && result.status !== "active" && result.status !== "revoked")
    || !(result.revision === null || typeof result.revision === "number" && Number.isSafeInteger(result.revision) && result.revision >= 1)
    || !(result.publicKeySha256 === null || digest(result.publicKeySha256))
    || (result.status === "untrusted" ? result.revision !== null || result.publicKeySha256 !== null
      : result.revision === null || result.publicKeySha256 === null)) return null;
  return result as unknown as PluginTrustState;
}
export function decodeGrantState(value: unknown): PluginGrantState | null {
  const result = object(value);
  if (!result || !keys(result, ["pluginId", "status", "revision", "packageSha256", "manifestSha256", "permissions", "destinations"])
    || typeof result.pluginId !== "string" || !id.test(result.pluginId) || result.pluginId.length > 121
    || (result.status !== "disabled" && result.status !== "enabled")
    || !(result.revision === null || typeof result.revision === "number" && Number.isSafeInteger(result.revision) && result.revision >= 1)
    || !(result.packageSha256 === null || digest(result.packageSha256))
    || !(result.manifestSha256 === null || digest(result.manifestSha256))
    || !Array.isArray(result.permissions) || result.permissions.length > 2 || !result.permissions.every((item) => typeof item === "string")
    || !destinations(result.destinations)
    || (result.status === "enabled" && (result.revision === null || result.packageSha256 === null || result.manifestSha256 === null))) return null;
  return result as unknown as PluginGrantState;
}

function randomHex16(): string {
  const bytes = new Uint8Array(16); globalThis.crypto.getRandomValues(bytes);
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
}
async function action(project: { readonly root: string; readonly projectId: string }, kind: string, fields: Record<string, unknown>, transport: PluginNativeTransport): Promise<NativePluginResult> {
  try { return decodeOutcome(await transport("connector_plugin_action", { request: { root: project.root, projectId: project.projectId, kind, ...fields } })); }
  catch { return { status: "failed" }; }
}

export async function refreshPluginReview(project: { readonly root: string; readonly projectId: string }, packageToken: string, transport: PluginNativeTransport = native): Promise<ReviewedPluginPackage | null> {
  const result = await action(project, "review", { packageToken }, transport);
  return result.status === "ok" ? decodePluginCandidateReview(result.value) : null;
}
export async function discardPluginReview(project: { readonly root: string; readonly projectId: string }, packageToken: string, transport: PluginNativeTransport = native): Promise<NativePluginResult> {
  if (!/^[0-9a-f]{64}$/.test(packageToken)) return { status: "failed" };
  return action(project, "discard", { packageToken }, transport);
}
export async function pluginTrustStatus(project: { readonly root: string; readonly projectId: string }, publisherKeyId: string, transport: PluginNativeTransport = native): Promise<PluginTrustState | null> {
  const result = await action(project, "trust-status", { publisherKeyId }, transport);
  const state = result.status === "ok" ? decodeTrustState(result.value) : null;
  return state?.publisherKeyId === publisherKeyId ? state : null;
}
export async function pluginGrantStatus(project: { readonly root: string; readonly projectId: string }, pluginId: string, transport: PluginNativeTransport = native): Promise<PluginGrantState | null> {
  const result = await action(project, "grant-status", { pluginId }, transport);
  const state = result.status === "ok" ? decodeGrantState(result.value) : null;
  return state?.pluginId === pluginId ? state : null;
}
export async function trustPluginPublisher(project: { readonly root: string; readonly projectId: string }, publisherKeyId: string, signal?: AbortSignal, transport: PluginNativeTransport = native): Promise<NativePluginResult> {
  if (signal?.aborted) return { status: "cancelled" };
  const operationId = randomHex16();
  const cancel = (): void => { void transport("cancel_connector_package_selection", { operationId }).catch(() => undefined); };
  signal?.addEventListener("abort", cancel, { once: true });
  try { return decodeOutcome(await transport("trust_connector_publisher", { request: { root: project.root, projectId: project.projectId, operationId, publisherKeyId } })); }
  catch { return { status: signal?.aborted ? "cancelled" : "failed" }; }
  finally { signal?.removeEventListener("abort", cancel); }
}
export async function enablePlugin(project: { readonly root: string; readonly projectId: string }, selected: ReviewedPluginPackage, trust: PluginTrustState, grant: PluginGrantState, transport: PluginNativeTransport = native): Promise<NativePluginResult> {
  const review = selected.review;
  if (review.runtimeStatus !== "ready" || review.trustStatus !== "active" || trust.status !== "active"
    || trust.revision === null || !trust.publicKeySha256 || grant.pluginId !== review.pluginId) return { status: "unavailable" };
  return action(project, "grant-enable", { packageToken: selected.packageToken }, transport);
}
export async function disablePlugin(project: { readonly root: string; readonly projectId: string }, grant: PluginGrantState, transport: PluginNativeTransport = native): Promise<NativePluginResult> {
  if (grant.status !== "enabled" || grant.revision === null) return { status: "unavailable" };
  return action(project, "grant-revoke", { pluginId: grant.pluginId }, transport);
}
export async function removePluginPublisherTrust(project: { readonly root: string; readonly projectId: string }, trust: PluginTrustState, transport: PluginNativeTransport = native): Promise<NativePluginResult> {
  if (trust.status !== "active" || trust.revision === null || !trust.publicKeySha256) return { status: "unavailable" };
  return action(project, "trust-revoke", { publisherKeyId: trust.publisherKeyId }, transport);
}
