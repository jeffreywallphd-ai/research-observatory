import { invoke } from "@tauri-apps/api/core";
import { decodeSourceIdentity, decodeSourceAnchorTarget, type SourceIdentity, type SourceAnchorTarget } from "./sourceAnchors";
import { viewerSourcesMatch } from "./documentViewer";

export interface ReferenceWork { readonly workId: string; readonly revisionId: string }
export interface ReferenceFeature {
  readonly name: string; readonly state: "available" | "not-reported" | "disputed";
  readonly score: number | null; readonly weight: number; readonly conflict: boolean;
}
export interface ReferenceCandidate {
  readonly target: ReferenceWork; readonly score: number; readonly features: readonly ReferenceFeature[];
  readonly flags: readonly string[]; readonly reviewState: "human-review-required";
  readonly algorithm: "scholarly-duplicate-ranking/1.0.0"; readonly featureVersion: "scholarly-duplicate-features/1.0.0";
  readonly configurationSha256: string;
}
export interface ReferencePreview {
  readonly referenceId: string; readonly nodeId: string; readonly order: number;
  readonly rawPreview: string; readonly rawLength: number; readonly rawTruncated: boolean;
  readonly fields: readonly { readonly name: "authors" | "year" | "title" | "venue"; readonly value: string;
    readonly valueCount: number; readonly truncated: boolean; readonly knowledgeStatus: "extracted" | "inferred" }[];
  readonly identifiers: readonly { readonly scheme: string; readonly observed: string; readonly truncated: boolean;
    readonly normalizedStatus: "valid" | "invalid" | "unsupported";
    readonly verificationState: "verified" | "unverified" | "disputed" | "invalid" | "not-reported"; readonly activeForMatching: boolean }[];
  readonly identifierCount: number; readonly linkState: "exact-linked" | "candidate" | "ambiguous" | "unresolved" | "non-scholarly" | "rejected";
  readonly target: ReferenceWork | null; readonly candidates: readonly ReferenceCandidate[]; readonly candidateCount: number;
  readonly matchFlags: readonly string[]; readonly anchor: SourceAnchorTarget | null; readonly anchorTruncated: boolean;
}
export interface ReferencePage {
  readonly schemaVersion: "1.0"; readonly projectId: string; readonly source: SourceIdentity;
  readonly documentRevisionId: string; readonly collectionId: string; readonly collectionRevisionId: string;
  readonly contentSha256: string; readonly structureSha256: string; readonly total: number;
  readonly afterOrder: number | null; readonly nextAfterOrder: number | null;
  readonly entries: readonly ReferencePreview[]; readonly scholarlyVerification: "unverified";
}
export interface ReferenceNotice {
  readonly schemaVersion: "1.0"; readonly projectId: string; readonly source: SourceIdentity;
  readonly documentRevisionId: string; readonly collectionId: string; readonly collectionRevisionId: string;
  readonly status: "unavailable"; readonly reasonCode: "viewer-resource-limit" | "references-unavailable";
  readonly scholarlyVerification: "unverified";
}
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u;
const digest = /^[0-9a-f]{64}$/u;
function object(value: unknown, keys: readonly string[]): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  if (Object.getPrototypeOf(value) !== Object.prototype && Object.getPrototypeOf(value) !== null) return null;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  if (Reflect.ownKeys(value).some(key => typeof key !== "string" || !("value" in descriptors[key]!))
    || Object.keys(descriptors).length !== keys.length || keys.some(key => !Object.hasOwn(descriptors, key))) return null;
  return Object.fromEntries(Object.entries(descriptors).map(([key, item]) => [key, item.value]));
}
function inertData(value: unknown, depth = 0, budget = { left: 4096 }): boolean {
  if (--budget.left < 0 || depth > 16) return false;
  if (value === null || typeof value === "string" || typeof value === "boolean") return true;
  if (typeof value === "number") return Number.isFinite(value);
  if (!value || typeof value !== "object") return false;
  if (Object.getPrototypeOf(value) !== (Array.isArray(value) ? Array.prototype : Object.prototype)
    && Object.getPrototypeOf(value) !== null) return false;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  return Reflect.ownKeys(value).every(key => typeof key === "string" && "value" in descriptors[key]!
    && inertData(descriptors[key]!.value, depth + 1, budget));
}
function array(value: unknown, max: number): value is unknown[] {
  if (!Array.isArray(value) || value.length > max) return false;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  return Reflect.ownKeys(value).every(key => typeof key === "string" && (key === "length" || /^(0|[1-9][0-9]*)$/u.test(key))
    && "value" in descriptors[key]!) && Object.keys(descriptors).length === value.length + 1;
}
function text(value: unknown, max: number): value is string {
  return typeof value === "string" && Array.from(value).length <= max
    && Array.from(value).every(point => point.length === 2 || point.charCodeAt(0) < 0xd800 || point.charCodeAt(0) > 0xdfff);
}
function count(value: unknown, max: number): value is number { return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= max; }
function id(value: unknown): value is string { return typeof value === "string" && uuid.test(value); }
function sha(value: unknown): value is string { return typeof value === "string" && digest.test(value); }
function strings(value: unknown): boolean { return array(value, 32) && value.every(item => text(item, 128)); }
function work(value: unknown): boolean { const item = object(value, ["workId", "revisionId"]); return Boolean(item && id(item["workId"]) && id(item["revisionId"])); }
function candidate(value: unknown): boolean {
  const item = object(value, ["target", "score", "features", "flags", "reviewState", "algorithm", "featureVersion", "configurationSha256"]);
  if (!item || !work(item["target"]) || !count(item["score"], 10000) || !strings(item["flags"])
    || item["reviewState"] !== "human-review-required" || item["algorithm"] !== "scholarly-duplicate-ranking/1.0.0"
    || item["featureVersion"] !== "scholarly-duplicate-features/1.0.0"
    || item["configurationSha256"] !== "b3e04c16bcfbb8588a718d55a94217a21a02ba1877fa9ea6ba187ebcdfc98dfc"
    || !array(item["features"], 7)) return false;
  const names = new Set<string>();
  return item["features"].every(value => {
    const feature = object(value, ["name", "state", "score", "weight", "conflict"]);
    if (!feature || typeof feature["name"] !== "string" || !["title", "authors", "year", "venue", "pages", "abstract", "identifiers"].includes(feature["name"])
      || names.has(feature["name"]) || !["available", "not-reported", "disputed"].includes(String(feature["state"]))
      || !(feature["score"] === null || count(feature["score"], 10000)) || !count(feature["weight"], 10000)
      || typeof feature["conflict"] !== "boolean") return false;
    names.add(feature["name"]); return true;
  });
}
function entry(value: unknown, page: Record<string, unknown>, source: SourceIdentity, revision: string, order: number): boolean {
  const item = object(value, ["referenceId", "nodeId", "order", "rawPreview", "rawLength", "rawTruncated", "fields", "identifiers", "identifierCount", "linkState", "target", "candidates", "candidateCount", "matchFlags", "anchor", "anchorTruncated"]);
  if (!item || !id(item["referenceId"]) || !id(item["nodeId"]) || item["order"] !== order
    || !text(item["rawPreview"], 1024) || !count(item["rawLength"], 65536)
    || item["rawLength"] < Array.from(item["rawPreview"]).length
    || item["rawTruncated"] !== (item["rawLength"] > Array.from(item["rawPreview"]).length)
    || !array(item["fields"], 4) || !array(item["identifiers"], 4) || !count(item["identifierCount"], 128)
    || item["identifiers"].length !== Math.min(4, item["identifierCount"])
    || !array(item["candidates"], 4) || !count(item["candidateCount"], 256)
    || item["candidates"].length !== Math.min(4, item["candidateCount"]) || !item["candidates"].every(candidate)
    || !strings(item["matchFlags"]) || typeof item["anchorTruncated"] !== "boolean"
    || !["exact-linked", "candidate", "ambiguous", "unresolved", "non-scholarly", "rejected"].includes(String(item["linkState"]))
    || (item["linkState"] === "exact-linked") !== (item["target"] !== null)
    || item["target"] !== null && !work(item["target"])
    || item["linkState"] === "exact-linked" && (item["candidateCount"] !== 0 || (item["matchFlags"] as unknown[]).length !== 0)) return false;
  const names = new Set<string>();
  if (!item["fields"].every(value => {
    const field = object(value, ["name", "value", "valueCount", "truncated", "knowledgeStatus"]);
    if (!field || typeof field["name"] !== "string" || !["authors", "year", "title", "venue"].includes(field["name"]) || names.has(field["name"])
      || !text(field["value"], 256) || !count(field["valueCount"], 256) || field["valueCount"] < 1 || typeof field["truncated"] !== "boolean"
      || !["extracted", "inferred"].includes(String(field["knowledgeStatus"]))) return false;
    names.add(field["name"]); return true;
  }) || !item["identifiers"].every(value => {
    const identifier = object(value, ["scheme", "observed", "truncated", "normalizedStatus", "verificationState", "activeForMatching"]);
    return Boolean(identifier && text(identifier["scheme"], 64) && /^[a-z][a-z0-9-]{0,63}$/u.test(identifier["scheme"])
      && text(identifier["observed"], 256) && typeof identifier["truncated"] === "boolean"
      && ["valid", "invalid", "unsupported"].includes(String(identifier["normalizedStatus"]))
      && ["verified", "unverified", "disputed", "invalid", "not-reported"].includes(String(identifier["verificationState"]))
      && typeof identifier["activeForMatching"] === "boolean");
  })) return false;
  if (item["anchor"] !== null) {
    const anchor = decodeSourceAnchorTarget(item["anchor"], source.projectId, revision);
    if (!anchor || anchor.nodeId !== item["nodeId"] || anchor.nodeKind !== "reference"
      || anchor.contentSha256 !== page["contentSha256"] || anchor.structureSha256 !== page["structureSha256"]
      || !viewerSourcesMatch(anchor.source, source)) return false;
  }
  return true;
}
export function decodeReferencePage(value: unknown, projectId: string, revisionId: string): ReferencePage | null {
  if (!inertData(value)) return null;
  const page = object(value, ["schemaVersion", "projectId", "source", "documentRevisionId", "collectionId", "collectionRevisionId", "contentSha256", "structureSha256", "total", "afterOrder", "nextAfterOrder", "entries", "scholarlyVerification"]);
  if (!page || page["schemaVersion"] !== "1.0" || page["projectId"] !== projectId || page["documentRevisionId"] !== revisionId
    || !id(revisionId) || !id(page["collectionId"]) || !id(page["collectionRevisionId"]) || page["collectionId"] === page["collectionRevisionId"]
    || !sha(page["contentSha256"]) || !sha(page["structureSha256"]) || !count(page["total"], 1000)
    || !(page["afterOrder"] === null || count(page["afterOrder"], 999)) || !array(page["entries"], 1)
    || page["scholarlyVerification"] !== "unverified") return null;
  const source = decodeSourceIdentity(page["source"], projectId);
  if (!source || source.documentRevisionId === revisionId) return null;
  const start = page["afterOrder"] === null ? 0 : Number(page["afterOrder"]) + 1;
  if (page["entries"].length !== Math.min(1, Math.max(0, page["total"] - start))
    || page["nextAfterOrder"] !== (page["entries"].length && start + 1 < page["total"] ? start : null)
    || !page["entries"].every(value => entry(value, page, source, revisionId, start))) return null;
  if (new TextEncoder().encode(JSON.stringify(page)).length > 65536) return null;
  return page as unknown as ReferencePage;
}
export function decodeReferenceNotice(value: unknown, projectId: string, revisionId: string): ReferenceNotice | null {
  if (!inertData(value)) return null;
  const notice = object(value, ["schemaVersion", "projectId", "source", "documentRevisionId", "collectionId", "collectionRevisionId", "status", "reasonCode", "scholarlyVerification"]);
  if (!notice || notice["schemaVersion"] !== "1.0" || notice["projectId"] !== projectId || notice["documentRevisionId"] !== revisionId
    || !id(revisionId) || !id(notice["collectionId"]) || !id(notice["collectionRevisionId"]) || notice["collectionId"] === notice["collectionRevisionId"]
    || notice["status"] !== "unavailable" || notice["reasonCode"] !== "viewer-resource-limit" && notice["reasonCode"] !== "references-unavailable"
    || notice["scholarlyVerification"] !== "unverified") return null;
  const source = decodeSourceIdentity(notice["source"], projectId);
  return source && source.documentRevisionId !== revisionId ? notice as unknown as ReferenceNotice : null;
}

export interface DocumentReferencePort {
  readonly read: (projectId: string, revisionId: string, expectedCollectionRevisionId: string | null, afterOrder: number | null) => Promise<unknown>;
  readonly enrich: (projectId: string, revisionId: string, commandId: string, expectedCollectionRevisionId: string | null) => Promise<unknown>;
}
async function request(command: string, fields: object): Promise<unknown> {
  if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) throw new Error("viewer-source-unavailable");
  return invoke<unknown>(command, { request: { schemaVersion: "1.0", ...fields } });
}
export const nativeDocumentReferencePort: DocumentReferencePort = {
  read: (projectId, revisionId, expectedCollectionRevisionId, afterOrder) => request("document_reader_references_read", { projectId, revisionId, expectedCollectionRevisionId, afterOrder }),
  enrich: (projectId, revisionId, commandId, expectedCollectionRevisionId) => request("document_reader_references_enrich", { projectId, revisionId, commandId, expectedCollectionRevisionId }),
};
