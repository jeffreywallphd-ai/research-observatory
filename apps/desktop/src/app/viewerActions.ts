import { invoke } from "@tauri-apps/api/core";
import { decodeViewerMetadata, viewerSourcesMatch, type ViewerMetadata, type ViewerSelector } from "./documentViewer";

export const readerActions = ["copy-quotation", "print-quotation", "export-quotation", "export-annotation", "open-external-original"] as const;
export type ReaderAction = typeof readerActions[number];
export interface ReaderActionRequest {
  readonly schemaVersion: "1.0"; readonly projectId: string; readonly selector: ViewerSelector;
  readonly operationId: string; readonly stage: "policy" | "denied-attempt" | "rights-review" | "execute";
  readonly action: ReaderAction; readonly anchorId: string | null;
  readonly expectedPolicyRevisionId: string | null; readonly commandId: string | null; readonly confirmed: boolean;
}
export interface ReaderPolicy {
  readonly metadata: ViewerMetadata; readonly action: ReaderAction; readonly anchorId: string | null;
  readonly policyRevisionId: string | null; readonly state: "ready" | "review-required" | "denied" | "unavailable";
  readonly reasonCode: string; readonly canReview: boolean;
}
export interface ReaderActionOutcome {
  readonly status: "policy" | "recorded" | "completed" | "partial" | "cancelled" | "denied" | "unavailable";
  readonly drained: boolean; readonly decision: ReaderPolicy | null;
  readonly review: { readonly policyRevisionId: string } | null;
}
export interface ReaderActionPort {
  readonly request: (request: ReaderActionRequest) => Promise<unknown>;
  readonly cancel: (projectId: string, operationId: string) => Promise<boolean>;
}

const id = (v: unknown): v is string => typeof v === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(v);
const code = (v: unknown): v is string => typeof v === "string" && /^[a-z][a-z0-9-]{0,119}$/.test(v);
function object(value: unknown, keys: readonly string[]): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value) || Reflect.ownKeys(value).length !== keys.length) return null;
  const fields = Object.getOwnPropertyDescriptors(value);
  if (keys.some(k => !fields[k] || !("value" in fields[k]!))) return null;
  return Object.fromEntries(keys.map(k => [k, fields[k]!.value as unknown]));
}
function policy(value: unknown, request: ReaderActionRequest, metadata: ViewerMetadata): ReaderPolicy | null {
  const o = object(value, ["schemaVersion", "metadata", "action", "anchorId", "policyRevisionId", "state", "reasonCode", "canReview", "requirements", "selectionLimitCodepoints"]);
  if (!o || o["schemaVersion"] !== "1.0" || o["action"] !== request.action || o["anchorId"] !== request.anchorId
    || o["policyRevisionId"] !== null && !id(o["policyRevisionId"]) || !code(o["reasonCode"])
    || typeof o["canReview"] !== "boolean" || o["selectionLimitCodepoints"] !== 2048
    || !["ready", "review-required", "denied", "unavailable"].includes(String(o["state"]))) return null;
  const selected = decodeViewerMetadata(o["metadata"], request.projectId, request.selector);
  if (!selected || !viewerSourcesMatch(metadata.source, selected.source)) return null;
  const uses = o["requirements"];
  const expected = [{ action: "inspect", purpose: "document-analysis", destinationKind: "local-project" }];
  if (request.action !== "open-external-original") expected.push({ action: "derive", purpose: "document-analysis", destinationKind: "local-project" });
  if (["copy-quotation", "print-quotation", "export-quotation"].includes(request.action)) expected.push({ action: "quote", purpose: "viewer-quotation", destinationKind: "local-project" });
  expected.push({ action: "export", purpose: `viewer-${request.action}`, destinationKind: "local-export" });
  if (!Array.isArray(uses) || uses.length !== expected.length || uses.some((v, index) => {
    const item = object(v, ["use", "code", "reasonCode"]), use = item && object(item["use"], ["action", "purpose", "destinationKind", "provider", "region", "shareGroup"]);
    const fixed = expected[index]!;
    return !item || !use || !code(item["reasonCode"]) || !["allow", "deny", "unknown", "require-confirmation"].includes(String(item["code"]))
      || use["action"] !== fixed.action || use["purpose"] !== fixed.purpose || use["destinationKind"] !== fixed.destinationKind
      || use["provider"] !== null || use["region"] !== null || use["shareGroup"] !== null
      || o["state"] === "ready" && !(item["code"] === "allow" || fixed.destinationKind === "local-export"
        && item["code"] === "require-confirmation" && item["reasonCode"] === "rights-further-authority-required");
  })) return null;
  if (o["canReview"] && o["state"] !== "review-required") return null;
  return { metadata: selected, action: request.action, anchorId: request.anchorId, policyRevisionId: o["policyRevisionId"] as string | null,
    state: o["state"] as ReaderPolicy["state"], reasonCode: o["reasonCode"], canReview: o["canReview"] };
}

export function decodeReaderAction(value: unknown, request: ReaderActionRequest, metadata: ViewerMetadata): ReaderActionOutcome | null {
  const o = object(value, ["schemaVersion", "projectId", "operationId", "action", "status", "drained", "decision", "review"]);
  if (!o || o["schemaVersion"] !== "1.0" || o["projectId"] !== request.projectId || o["operationId"] !== request.operationId
    || o["action"] !== request.action || typeof o["drained"] !== "boolean"
    || !["policy", "recorded", "completed", "partial", "cancelled", "denied", "unavailable"].includes(String(o["status"]))) return null;
  const decision = o["decision"] === null ? null : policy(o["decision"], request, metadata);
  const review = o["review"] === null ? null : object(o["review"], ["schemaVersion", "metadata", "action", "policyRevisionId", "status"]);
  if (o["decision"] !== null && !decision || o["review"] !== null && !review) return null;
  if (review) {
    const selected = decodeViewerMetadata(review["metadata"], request.projectId, request.selector);
    if (review["schemaVersion"] !== "1.0" || review["action"] !== request.action || review["status"] !== "recorded"
      || !id(review["policyRevisionId"]) || !selected || !viewerSourcesMatch(metadata.source, selected.source)) return null;
  }
  const status = o["status"] as ReaderActionOutcome["status"];
  if (status === "policy" && (!decision || review || !["policy", "denied-attempt"].includes(request.stage))
    || status === "recorded" && (!review || decision || request.stage !== "rights-review")
    || status === "completed" && (decision || review || request.stage !== "execute")
    || status === "partial" && (decision || review || request.stage !== "execute")
    || !["policy", "recorded"].includes(status) && (decision || review)
    || ["policy", "recorded", "completed"].includes(status) && !o["drained"]) return null;
  return { status, drained: o["drained"], decision, review: review ? { policyRevisionId: review["policyRevisionId"] as string } : null };
}

export const nativeReaderActionPort: ReaderActionPort = {
  request: request => invoke<unknown>("document_viewer_action", { request }),
  async cancel(projectId, operationId) {
    try { return await invoke<unknown>("document_viewer_action_cancel", { request: { schemaVersion: "1.0", projectId, operationId } }) === true; }
    catch { return false; }
  },
};
