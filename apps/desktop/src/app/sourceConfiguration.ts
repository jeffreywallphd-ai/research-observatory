import { invoke } from "@tauri-apps/api/core";

export type ScholarlyProvider = "openalex" | "crossref" | "unpaywall" | "semantic-scholar";
export type ConfigurationOutcome = { readonly status: "saved" | "cancelled" | "unavailable" | "conflict" | "rejected" | "save-unconfirmed" };
export function decodeConfigurationOutcome(value: unknown): ConfigurationOutcome | null {
  if (!value || typeof value !== "object" || Array.isArray(value) || Reflect.ownKeys(value).length !== 1) return null;
  const status = Object.getOwnPropertyDescriptor(value, "status");
  if (!status || !("value" in status) || !["saved", "cancelled", "unavailable", "conflict", "rejected", "save-unconfirmed"].includes(status.value)) return null;
  return { status: status.value } as ConfigurationOutcome;
}
export function configurationMessage(outcome: ConfigurationOutcome): string {
  switch (outcome.status) {
    case "saved": return "Source settings saved privately on this computer. No connection was tested and no project permissions changed.";
    case "cancelled": return "Configuration cancelled before saving. The prior source settings are unchanged.";
    case "unavailable": return "Private source configuration is unavailable. Use the installed desktop window with an open writable project and a ready local service.";
    case "conflict": return "Source settings changed while the form was open. Reopen Configure to review the current state; this save did not replace it.";
    case "rejected": return "The source settings were not accepted. Reopen Configure and check the contact address or key format.";
    case "save-unconfirmed": return "The save outcome could not be confirmed. Reopen Configure to check the current settings before trying again.";
  }
}

let pending = false;
export async function openSourceTerms(providerId: ScholarlyProvider): Promise<void> {
  await invoke("open_scholarly_source_terms", { providerId });
}

export async function configureSource(project: { readonly root: string; readonly projectId: string }, providerId: ScholarlyProvider, signal?: AbortSignal): Promise<ConfigurationOutcome> {
  if (signal?.aborted) return { status: "cancelled" };
  if (typeof globalThis.window === "undefined" || !("__TAURI_INTERNALS__" in globalThis.window) || pending) return { status: "unavailable" };
  const operationId = Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, "0")).join("");
  // Explicit picking of fields prevents a caller's extra properties from
  // becoming a private-configuration input or a native filesystem capability.
  const request = { operationId, root: project.root, projectId: project.projectId, providerId };
  const cancel = (): void => { void invoke("cancel_scholarly_source_configuration", { operationId }).catch(() => undefined); };
  pending = true; signal?.addEventListener("abort", cancel, { once: true });
  try { return decodeConfigurationOutcome(await invoke("configure_scholarly_source", { request })) ?? { status: "save-unconfirmed" }; }
  catch { return { status: "save-unconfirmed" }; }
  finally { pending = false; signal?.removeEventListener("abort", cancel); }
}
