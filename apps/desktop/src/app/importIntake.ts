import { invoke } from "@tauri-apps/api/core";
import { decodeImportPreviewItem, type ImportPreviewItem } from "@research-observatory/contracts/core-api";

export interface ImportIntakeOptions {
  readonly formatName: ImportPreviewItem["formatName"];
  readonly encoding: ImportPreviewItem["encoding"];
  readonly delimiter: "," | "\t" | ";";
  readonly localUseConfirmed: boolean;
}
export type ImportIntakeOutcome = { readonly status: "prepared"; readonly preview: ImportPreviewItem }
  | { readonly status: "cancelled" | "unavailable" | "failed" };

function data(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  if (Reflect.ownKeys(value).some((key) => typeof key !== "string" || !("value" in descriptors[key]!))) return null;
  return Object.fromEntries(Object.entries(descriptors).map(([key, descriptor]) => [key, descriptor.value]));
}
function keys(value: Record<string, unknown>, expected: readonly string[]): boolean {
  return Object.keys(value).length === expected.length && expected.every((key) => Object.hasOwn(value, key));
}

export function decodeImportOutcome(value: unknown, options: ImportIntakeOptions): ImportIntakeOutcome | null {
  try {
    const item = data(value);
    if (!item) return null;
    if (keys(item, ["status"]) && (item.status === "cancelled" || item.status === "unavailable" || item.status === "failed")) return { status: item.status };
    if (item.status !== "prepared" || !keys(item, ["status", "sourceName", "preview"])) return null;
    const status = data(item.preview);
    if (!status || !keys(status, ["previewId", "state", "byteLength", "chunkCount", "jobId", "jobState"])) return null;
    const preview = decodeImportPreviewItem({ ...status, sourceName: item.sourceName, formatName: options.formatName, encoding: options.encoding });
    return preview ? { status: "prepared", preview } : null;
  } catch { return null; }
}

let pending = false;
export type ImportReportOutcome = { readonly status: "saved"; readonly filename: string; readonly byteLength: number }
  | { readonly status: "cancelled" | "unavailable" | "failed" };

export async function saveImportReport(address: { readonly root: string; readonly projectId: string; readonly previewId: string; readonly revision: number }, signal?: AbortSignal): Promise<ImportReportOutcome> {
  if (signal?.aborted) return { status: "cancelled" };
  if (typeof globalThis.window === "undefined" || !("__TAURI_INTERNALS__" in globalThis.window) || pending) return { status: "unavailable" };
  const bytes = new Uint8Array(16); globalThis.crypto.getRandomValues(bytes);
  const operationId = Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
  const request = { root: address.root, projectId: address.projectId, previewId: address.previewId, revision: address.revision, operationId };
  const cancel = (): void => { void invoke("cancel_import_file", { operationId }).catch(() => undefined); };
  pending = true; signal?.addEventListener("abort", cancel, { once: true });
  try {
    const value = data(await invoke("save_import_report", { request }));
    if (value && keys(value, ["status"]) && (value.status === "cancelled" || value.status === "unavailable" || value.status === "failed")) return { status: value.status };
    if (value && keys(value, ["status", "filename", "byteLength"]) && value.status === "saved"
      && value.filename === `import-diagnostics-${operationId}.csv` && typeof value.byteLength === "number"
      && Number.isSafeInteger(value.byteLength) && value.byteLength > 0 && value.byteLength <= 268435456) {
      // A late cancellation cannot undo a file already published by native code.
      return { status: "saved", filename: value.filename, byteLength: value.byteLength };
    }
    return { status: "failed" };
  } catch { return { status: "failed" }; }
  finally { signal?.removeEventListener("abort", cancel); pending = false; }
}

export async function chooseImportSource(
  project: { readonly root: string; readonly projectId: string }, options: ImportIntakeOptions, signal?: AbortSignal,
): Promise<ImportIntakeOutcome> {
  if (signal?.aborted) return { status: "cancelled" };
  if (typeof globalThis.window === "undefined" || !("__TAURI_INTERNALS__" in globalThis.window) || pending) return { status: "unavailable" };
  if (!options.localUseConfirmed) return { status: "failed" };
  const selected = { ...options };
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  const operationId = Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
  const request = { root: project.root, projectId: project.projectId, operationId, formatName: selected.formatName, encoding: selected.encoding, delimiter: selected.delimiter,
    rights: Object.fromEntries(["store", "inspect", "index", "derive", "model-use", "quote", "export", "share"].map((action) => [action,
      action === "store" || action === "inspect" ? { value: "permitted", basis: "researcher-confirmed" } : { value: "unknown", basis: "not-reported" }])) };
  const cancel = (): void => { void invoke("cancel_import_file", { operationId }).catch(() => undefined); };
  pending = true;
  signal?.addEventListener("abort", cancel, { once: true });
  try {
    // Return a late prepared identity to the owner solely for best-effort Core
    // cancellation; it must not be rendered after the owner's generation changes.
    const result = decodeImportOutcome(await invoke("import_selected_file", { request }), selected);
    return result ?? { status: signal?.aborted ? "cancelled" : "failed" };
  } catch { return { status: signal?.aborted ? "cancelled" : "failed" }; }
  finally { signal?.removeEventListener("abort", cancel); pending = false; }
}
