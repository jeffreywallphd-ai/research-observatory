import { invoke } from "@tauri-apps/api/core";

export type DirectoryPurpose = "create-parent" | "open-project";
export interface DirectoryPickerRequest {
  readonly purpose: DirectoryPurpose;
  readonly previousLocation?: string;
}
export type DirectorySelection = { readonly status: "selected"; readonly path: string }
  | { readonly status: "cancelled" | "unavailable" | "failed" };
export type DefaultProjectParent = { readonly status: "available"; readonly path: string }
  | { readonly status: "unavailable" | "failed" };

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function exactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  const actual = Reflect.ownKeys(value);
  return actual.length === keys.length && actual.every((key) => typeof key === "string" && keys.includes(key));
}

// Lexical transport validation only. The native owner and Core independently
// validate existence, canonicality, locality, access and filesystem authority.
function localDirectory(value: unknown): value is string {
  if (typeof value !== "string" || value.length > 4096 || !value.isWellFormed()
    || !/^[a-z]:[\\/]/i.test(value) || /[\x00-\x1f\x7f-\x9f<>"|?*]/.test(value)
    || value.slice(2).includes(":")) return false;
  const parts = value.slice(3).replaceAll("\\", "/").split("/");
  return parts.every((part, index) => (part.length > 0 || index === parts.length - 1)
    && part !== "." && part !== ".." && !/[. ]$/.test(part));
}

export function decodeDirectorySelection(value: unknown): DirectorySelection | null {
  try {
    if (!record(value)) return null;
    if (value.status === "selected" && exactKeys(value, ["status", "path"]) && localDirectory(value.path)) {
      return { status: "selected", path: value.path };
    }
    if (exactKeys(value, ["status"]) && (value.status === "cancelled" || value.status === "unavailable" || value.status === "failed")) {
      return { status: value.status };
    }
  } catch { /* Hostile property access is not an application diagnostic. */ }
  return null;
}

export function decodeDefaultProjectParent(value: unknown): DefaultProjectParent | null {
  try {
    if (!record(value)) return null;
    if (value.status === "available" && exactKeys(value, ["status", "path"]) && localDirectory(value.path)) {
      return { status: "available", path: value.path };
    }
    if (exactKeys(value, ["status"]) && (value.status === "unavailable" || value.status === "failed")) {
      return { status: value.status };
    }
  } catch { /* A failed lookup must not leak native content into the view. */ }
  return null;
}

function nativeHost(): boolean {
  return typeof globalThis.window !== "undefined" && "__TAURI_INTERNALS__" in globalThis.window;
}

let pickerPending = false;

export async function chooseProjectDirectory(request: DirectoryPickerRequest, signal?: AbortSignal): Promise<DirectorySelection> {
  if (signal?.aborted) return { status: "cancelled" };
  try {
    if (!record(request) || (request.purpose !== "create-parent" && request.purpose !== "open-project")
      || !exactKeys(request, "previousLocation" in request ? ["purpose", "previousLocation"] : ["purpose"])
      || ("previousLocation" in request && !localDirectory(request.previousLocation))) return { status: "failed" };
  } catch { return { status: "failed" }; }
  if (!nativeHost() || pickerPending) return { status: "unavailable" };
  pickerPending = true;
  try {
    const result = await invoke<unknown>("choose_project_directory", { request });
    return signal?.aborted ? { status: "cancelled" } : decodeDirectorySelection(result) ?? { status: "failed" };
  } catch {
    return signal?.aborted ? { status: "cancelled" } : { status: "failed" };
  } finally {
    // Aborting a form does not imply that the native modal has finished.
    pickerPending = false;
  }
}

export async function defaultProjectParent(signal?: AbortSignal): Promise<DefaultProjectParent> {
  if (signal?.aborted || !nativeHost()) return { status: "unavailable" };
  try {
    const result = await invoke<unknown>("default_project_parent");
    return signal?.aborted ? { status: "unavailable" } : decodeDefaultProjectParent(result) ?? { status: "failed" };
  } catch { return { status: "failed" }; }
}

const CHILD_NAME = /^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$/;
const DEVICE_NAME = /^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])$/;

export function projectDirectoryName(displayName: string, fallbackId: string): string {
  if (!/^[a-f0-9]{12}$/.test(fallbackId)) throw new TypeError("Invalid folder suggestion identity.");
  if (!displayName.trim()) return "";
  let slug = displayName.normalize("NFKD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  if (!slug) return `project-${fallbackId}`;
  slug = slug.slice(0, 64).replace(/-+$/g, "");
  return DEVICE_NAME.test(slug) ? `project-${slug}` : slug;
}

export function projectDestination(parent: string, directoryName: string): string {
  if (!localDirectory(parent) || !CHILD_NAME.test(directoryName)) return "";
  const separator = /[\\/]$/.test(parent) ? "" : parent.includes("\\") ? "\\" : "/";
  const destination = `${parent}${separator}${directoryName}`;
  // A created project must still fit the unchanged Core open-root contract.
  return destination.length <= 4096 ? destination : "";
}
