import { invoke } from "@tauri-apps/api/core";
import { decodeSourceIdentity, decodeSourceAnchorTarget, type SourceIdentity, type SourceAnchorTarget } from "./sourceAnchors";
import { viewerSourcesMatch } from "./documentViewer";
import type { ReferenceWork } from "./documentReferences";

type Resolution = "candidate" | "ambiguous" | "unresolved";
interface Range { readonly start: number; readonly end: number }
export interface CitationReference { readonly referenceId: string; readonly nodeId: string; readonly order: number;
  readonly linkState: "exact-linked" | "candidate" | "ambiguous" | "unresolved" | "non-scholarly" | "rejected"; readonly target: ReferenceWork | null }
export interface CitationContextPreview { readonly nodeId: string; readonly projectionId: string; readonly normalizedRange: Range;
  readonly markerRange: Range | null; readonly textPreview: string; readonly textLength: number; readonly previewStart: number;
  readonly truncated: boolean; readonly basis: "source-element" | "sentence-pattern" }
export interface CitationPreview { readonly order: number; readonly canonicalCitationId: string | null; readonly nodeId: string;
  readonly textOffset: number; readonly nodeTextStart: number; readonly markerPreview: string; readonly markerLength: number;
  readonly markerTruncated: boolean; readonly style: "reported" | "numeric" | "author-year" | "narrative" | "superscript";
  readonly knowledgeStatus: "extracted" | "inferred"; readonly resolution: Resolution;
  readonly targets: readonly { readonly label: string; readonly resolution: Resolution; readonly referenceCount: number; readonly references: readonly CitationReference[] }[];
  readonly targetCount: number; readonly anchor: SourceAnchorTarget | null; readonly anchorTruncated: boolean;
  readonly paragraph: CitationContextPreview | null; readonly sentence: CitationContextPreview | null;
  readonly contextReason: "available" | "not-reported" | "normalization-boundary" | "empty-marker" | "excluded-region";
  readonly confidence: { readonly state: string; readonly value: number | null } }
export interface CitationPage { readonly schemaVersion: "1.0"; readonly projectId: string; readonly source: SourceIdentity;
  readonly documentRevisionId: string; readonly collectionId: string; readonly collectionRevisionId: string;
  readonly referenceCollectionId: string; readonly referenceCollectionRevisionId: string;
  readonly contentSha256: string; readonly structureSha256: string; readonly total: number;
  readonly afterOrder: number | null; readonly nextAfterOrder: number | null; readonly entries: readonly CitationPreview[];
  readonly scholarlyVerification: "unverified" }
export interface CitationNotice { readonly schemaVersion: "1.0"; readonly projectId: string; readonly source: SourceIdentity;
  readonly documentRevisionId: string; readonly collectionId: string; readonly collectionRevisionId: string;
  readonly status: "unavailable"; readonly reasonCode: "viewer-resource-limit" | "citations-unavailable"; readonly scholarlyVerification: "unverified" }
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u;
const digest = /^[0-9a-f]{64}$/u;
function inert(value: unknown, depth = 0, budget = { left: 4096 }): boolean {
  if (--budget.left < 0 || depth > 16) return false;
  if (value === null || typeof value === "string" || typeof value === "boolean") return true;
  if (typeof value === "number") return Number.isFinite(value);
  if (!value || typeof value !== "object") return false;
  if (Object.getPrototypeOf(value) !== (Array.isArray(value) ? Array.prototype : Object.prototype) && Object.getPrototypeOf(value) !== null) return false;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  return Reflect.ownKeys(value).every(key => typeof key === "string" && "value" in descriptors[key]!
    && inert(descriptors[key]!.value, depth + 1, budget));
}
function object(value: unknown, keys: readonly string[]): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const d = Object.getOwnPropertyDescriptors(value);
  if (Reflect.ownKeys(value).length !== keys.length || keys.some(k => !Object.hasOwn(d, k) || !("value" in d[k]!))) return null;
  return Object.fromEntries(keys.map(k => [k, d[k]!.value]));
}
function id(value: unknown): value is string { return typeof value === "string" && uuid.test(value); }
function sha(value: unknown): value is string { return typeof value === "string" && digest.test(value); }
function count(value: unknown, max = Number.MAX_SAFE_INTEGER): value is number { return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= max; }
function text(value: unknown, max: number): value is string { return typeof value === "string" && Array.from(value).length <= max
  && Array.from(value).every(p => p.length === 2 || p.charCodeAt(0) < 0xd800 || p.charCodeAt(0) > 0xdfff); }
function array(value: unknown, max: number): value is unknown[] { return Array.isArray(value) && value.length <= max
  && Reflect.ownKeys(value).length === value.length + 1 && Array.from({ length: value.length }, (_, i) => i).every(i => Object.hasOwn(value, i)); }
function one(value: unknown, options: readonly string[]): boolean { return typeof value === "string" && options.includes(value); }
function range(value: unknown): Range | null { const r = object(value, ["start", "end"]); return r && count(r["start"]) && count(r["end"]) && r["start"] <= r["end"] ? r as unknown as Range : null; }
function context(value: unknown): boolean {
  if (value === null) return true;
  const c = object(value, ["nodeId", "projectionId", "normalizedRange", "markerRange", "textPreview", "textLength", "previewStart", "truncated", "basis"]);
  if (!c || !id(c["nodeId"]) || !id(c["projectionId"]) || !text(c["textPreview"], 1024) || !count(c["textLength"], 65536)
    || !count(c["previewStart"]) || c["truncated"] !== (c["textLength"] > Array.from(c["textPreview"]).length)
    || !one(c["basis"], ["source-element", "sentence-pattern"])) return false;
  const r = range(c["normalizedRange"]), marker = c["markerRange"] === null ? null : range(c["markerRange"]);
  return Boolean(r && r.end - r.start === c["textLength"] && c["previewStart"] >= r.start && c["previewStart"] + Array.from(c["textPreview"]).length <= r.end
    && (c["markerRange"] === null || marker && r.start <= marker.start && marker.start < marker.end && marker.end <= r.end));
}
function reference(value: unknown): boolean {
  const r = object(value, ["referenceId", "nodeId", "order", "linkState", "target"]);
  if (!r || !id(r["referenceId"]) || !id(r["nodeId"]) || !count(r["order"], 999) || !one(r["linkState"], ["exact-linked", "candidate", "ambiguous", "unresolved", "non-scholarly", "rejected"])
    || (r["linkState"] === "exact-linked") !== (r["target"] !== null)) return false;
  if (r["target"] === null) return true;
  const w = object(r["target"], ["workId", "revisionId"]); return Boolean(w && id(w["workId"]) && id(w["revisionId"]));
}
function entry(value: unknown, page: Record<string, unknown>, source: SourceIdentity, revision: string, order: number): boolean {
  const e = object(value, ["order", "canonicalCitationId", "nodeId", "textOffset", "nodeTextStart", "markerPreview", "markerLength", "markerTruncated", "style", "knowledgeStatus", "resolution", "targets", "targetCount", "anchor", "anchorTruncated", "paragraph", "sentence", "contextReason", "confidence"]);
  if (!e || e["order"] !== order || !id(e["nodeId"]) || !(e["canonicalCitationId"] === null || id(e["canonicalCitationId"]))
    || !count(e["textOffset"]) || !count(e["nodeTextStart"]) || !text(e["markerPreview"], 256) || !count(e["markerLength"], 65536)
    || e["markerLength"] < Array.from(e["markerPreview"]).length || e["markerTruncated"] !== (e["markerLength"] > Array.from(e["markerPreview"]).length)
    || !one(e["style"], ["reported", "numeric", "author-year", "narrative", "superscript"]) || !one(e["knowledgeStatus"], ["extracted", "inferred"])
    || (e["knowledgeStatus"] === "extracted") !== (e["canonicalCitationId"] !== null) || !one(e["resolution"], ["candidate", "ambiguous", "unresolved"])
    || !count(e["targetCount"], 128) || !array(e["targets"], 4) || e["targets"].length !== Math.min(4, e["targetCount"])
    || !context(e["paragraph"]) || !context(e["sentence"]) || !one(e["contextReason"], ["available", "not-reported", "normalization-boundary", "empty-marker", "excluded-region"])
    || typeof e["anchorTruncated"] !== "boolean") return false;
  const confidence = object(e["confidence"], ["state", "value"]);
  if (!confidence || !one(confidence["state"], ["reported", "unknown", "not-reported", "not-applicable", "unavailable"])
    || (confidence["state"] === "reported" ? typeof confidence["value"] !== "number" || confidence["value"] < 0 || confidence["value"] > 1 : confidence["value"] !== null)) return false;
  const states: unknown[] = [];
  if (!e["targets"].every(value => {
    const t = object(value, ["label", "resolution", "referenceCount", "references"]);
    if (!t || !text(t["label"], 512) || !t["label"] || !count(t["referenceCount"], 1000) || !array(t["references"], 4)
      || t["references"].length !== Math.min(4, t["referenceCount"]) || !t["references"].every(reference)
      || t["resolution"] !== (!t["referenceCount"] ? "unresolved" : t["referenceCount"] === 1 ? "candidate" : "ambiguous")
      || new Set(t["references"].map(r => (r as CitationReference).referenceId)).size !== t["references"].length) return false;
    states.push(t["resolution"]); return true;
  })) return false;
  if (e["targetCount"] === states.length && e["resolution"] !== (!states.length || states.includes("unresolved") ? "unresolved" : states.includes("ambiguous") ? "ambiguous" : "candidate")) return false;
  if (e["anchor"] !== null) {
    const a = decodeSourceAnchorTarget(e["anchor"], source.projectId, revision);
    if (!a || a.nodeId !== e["nodeId"] || !viewerSourcesMatch(a.source, source) || a.contentSha256 !== page["contentSha256"] || a.structureSha256 !== page["structureSha256"]
      || !a.textPosition || a.textPosition.start !== e["nodeTextStart"] + e["textOffset"]) return false;
  }
  return true;
}
export function decodeCitationPage(value: unknown, projectId: string, revisionId: string): CitationPage | null {
  if (!inert(value)) return null;
  const p = object(value, ["schemaVersion", "projectId", "source", "documentRevisionId", "collectionId", "collectionRevisionId", "referenceCollectionId", "referenceCollectionRevisionId", "contentSha256", "structureSha256", "total", "afterOrder", "nextAfterOrder", "entries", "scholarlyVerification"]);
  if (!p || p["schemaVersion"] !== "1.0" || p["projectId"] !== projectId || p["documentRevisionId"] !== revisionId || !id(revisionId)
    || !id(p["collectionId"]) || !id(p["collectionRevisionId"]) || p["collectionId"] === p["collectionRevisionId"]
    || !id(p["referenceCollectionId"]) || !id(p["referenceCollectionRevisionId"]) || p["referenceCollectionId"] === p["referenceCollectionRevisionId"]
    || !sha(p["contentSha256"]) || !sha(p["structureSha256"]) || !count(p["total"], 1000) || !(p["afterOrder"] === null || count(p["afterOrder"], 999))
    || !array(p["entries"], 1) || p["scholarlyVerification"] !== "unverified") return null;
  const source = decodeSourceIdentity(p["source"], projectId), start = p["afterOrder"] === null ? 0 : Number(p["afterOrder"]) + 1;
  if (!source || source.documentRevisionId === revisionId || p["entries"].length !== Math.min(1, Math.max(0, p["total"] - start))
    || p["nextAfterOrder"] !== (p["entries"].length && start + 1 < p["total"] ? start : null)
    || !p["entries"].every(v => entry(v, p, source, revisionId, start)) || new TextEncoder().encode(JSON.stringify(p)).length > 65536) return null;
  return p as unknown as CitationPage;
}
export function decodeCitationNotice(value: unknown, projectId: string, revisionId: string): CitationNotice | null {
  if (!inert(value)) return null;
  const n = object(value, ["schemaVersion", "projectId", "source", "documentRevisionId", "collectionId", "collectionRevisionId", "status", "reasonCode", "scholarlyVerification"]);
  if (!n || n["schemaVersion"] !== "1.0" || n["projectId"] !== projectId || n["documentRevisionId"] !== revisionId || !id(revisionId)
    || !id(n["collectionId"]) || !id(n["collectionRevisionId"]) || n["collectionId"] === n["collectionRevisionId"] || n["status"] !== "unavailable"
    || !one(n["reasonCode"], ["viewer-resource-limit", "citations-unavailable"]) || n["scholarlyVerification"] !== "unverified") return null;
  const s = decodeSourceIdentity(n["source"], projectId); return s && s.documentRevisionId !== revisionId ? n as unknown as CitationNotice : null;
}
export interface DocumentCitationPort {
  readonly read: (projectId: string, revisionId: string, expected: string | null, after: number | null) => Promise<unknown>;
  readonly enrich: (projectId: string, revisionId: string, commandId: string, referenceRevision: string, expected: string | null) => Promise<unknown>;
}
async function request(command: string, fields: object): Promise<unknown> {
  if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) throw new Error("viewer-source-unavailable");
  return invoke<unknown>(command, { request: { schemaVersion: "1.0", ...fields } });
}
export const nativeDocumentCitationPort: DocumentCitationPort = {
  read: (projectId, revisionId, expectedCollectionRevisionId, afterOrder) => request("document_reader_citations_read", { projectId, revisionId, expectedCollectionRevisionId, afterOrder }),
  enrich: (projectId, revisionId, commandId, referenceCollectionRevisionId, expectedCollectionRevisionId) => request("document_reader_citations_enrich", { projectId, revisionId, commandId, referenceCollectionRevisionId, expectedCollectionRevisionId }),
};
