import { invoke } from "@tauri-apps/api/core";
import { decodeSourceIdentity, type SourceIdentity } from "./sourceAnchors";

interface Range { readonly start: number; readonly end: number }
export interface StructureJump { readonly nodeId: string; readonly nodeKind: string; readonly textOffset: number;
  readonly nodeTextStart: number; readonly normalizedRange: Range | null; readonly pageNumber: number | null }
interface Confidence { readonly state: string; readonly value: number | null }
export interface StructureTextPreview { readonly nodeId: string; readonly textPreview: string; readonly textLength: number;
  readonly truncated: boolean; readonly jump: StructureJump }
export interface TableCellPreview extends StructureTextPreview { readonly cellOrder: number; readonly row: number;
  readonly column: number; readonly rowSpan: number; readonly columnSpan: number; readonly headerState: string;
  readonly confidence: Confidence; readonly triage: "unknown-confidence" | "low-confidence" | "reported-confidence" }
export interface StructureExclusion { readonly nodeId: string; readonly actorId: string; readonly commandId: string;
  readonly rationale: string; readonly occurredAt: string }
type StructurePreview = { readonly kind: "unavailable"; readonly reason: string } | {
  readonly kind: "source-page-region"; readonly sourceRevisionId: string; readonly objectSha256: string;
  readonly nodeId: string; readonly basis: "object" | "cell"; readonly scholarlyVerification: "unverified";
  readonly locator: { readonly kind: "page-region"; readonly pageIndex: number; readonly x0: number; readonly y0: number;
    readonly x1: number; readonly y1: number; readonly unit: "points"; readonly origin: "top-left"; readonly frame: "unrotated-source-page" } };
export interface TableFigurePreview { readonly nodeId: string; readonly kind: "table" | "figure"; readonly order: number;
  readonly jump: StructureJump; readonly captionState: "reported" | "ambiguous" | "not-reported" | "unavailable";
  readonly captionCount: number; readonly captions: readonly StructureTextPreview[]; readonly labelCount: number;
  readonly labels: readonly StructureTextPreview[]; readonly rows: number | null; readonly columns: number | null;
  readonly gridState: "reported" | "ambiguous" | null; readonly cellCount: number; readonly afterCell: number | null;
  readonly nextAfterCell: number | null; readonly cells: readonly TableCellPreview[]; readonly confidence: Confidence;
  readonly preview: StructurePreview; readonly retainedPreviewState: string; readonly warnings: readonly string[];
  readonly excluded: boolean; readonly exclusion: StructureExclusion | null }
export interface TableFigurePage { readonly schemaVersion: "1.0"; readonly projectId: string; readonly source: SourceIdentity;
  readonly documentRevisionId: string; readonly collectionId: string; readonly collectionRevisionId: string;
  readonly contentSha256: string; readonly structureSha256: string; readonly total: number; readonly afterOrder: number | null;
  readonly nextAfterOrder: number | null; readonly entries: readonly TableFigurePreview[]; readonly scholarlyVerification: "unverified" }
export interface TableFigureNotice { readonly schemaVersion: "1.0"; readonly projectId: string; readonly source: SourceIdentity;
  readonly documentRevisionId: string; readonly collectionId: string; readonly collectionRevisionId: string;
  readonly status: "unavailable"; readonly reasonCode: "viewer-resource-limit" | "table-figures-unavailable"; readonly scholarlyVerification: "unverified" }

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u;
const digest = /^[0-9a-f]{64}$/u;
function inert(value: unknown, depth = 0, budget = { left: 4096 }): boolean {
  if (--budget.left < 0 || depth > 16) return false;
  if (value === null || typeof value === "boolean") return true;
  if (typeof value === "string") return value.length <= 65536;
  if (typeof value === "number") return Number.isFinite(value);
  if (!value || typeof value !== "object" || Array.isArray(value) && value.length > 4096) return false;
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== (Array.isArray(value) ? Array.prototype : Object.prototype) && prototype !== null) return false;
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
function text(value: unknown, max: number): value is string { return typeof value === "string" && value.length <= max * 2 && Array.from(value).length <= max
  && Array.from(value).every(p => p.length === 2 || p.charCodeAt(0) < 0xd800 || p.charCodeAt(0) > 0xdfff); }
function array(value: unknown, max: number): value is unknown[] { return Array.isArray(value) && value.length <= max
  && Reflect.ownKeys(value).length === value.length + 1 && Array.from({ length: value.length }, (_, i) => i).every(i => Object.hasOwn(value, i)); }
function one(value: unknown, options: readonly string[]): boolean { return typeof value === "string" && options.includes(value); }
function range(value: unknown): Range | null { const r = object(value, ["start", "end"]); return r && count(r["start"]) && count(r["end"]) && r["start"] <= r["end"] ? r as unknown as Range : null; }
function quality(value: unknown): Confidence | null {
  const c = object(value, ["state", "value"]);
  return c && one(c["state"], ["reported", "unknown", "not-reported", "not-applicable", "unavailable"])
    && (c["state"] === "reported" ? typeof c["value"] === "number" && c["value"] >= 0 && c["value"] <= 1 : c["value"] === null)
    ? c as unknown as Confidence : null;
}
function jump(value: unknown): StructureJump | null {
  const j = object(value, ["nodeId", "nodeKind", "textOffset", "nodeTextStart", "normalizedRange", "pageNumber"]);
  if (!j || !id(j["nodeId"]) || !one(j["nodeKind"], ["region", "title", "abstract", "section", "paragraph", "sentence", "list", "list-item", "footnote", "reference", "citation-marker", "table", "table-cell", "figure", "caption", "equation", "unknown"])
    || !count(j["textOffset"]) || !count(j["nodeTextStart"]) || !(j["pageNumber"] === null || count(j["pageNumber"], 500) && j["pageNumber"] > 0)) return null;
  const r = j["normalizedRange"] === null ? null : range(j["normalizedRange"]);
  return j["normalizedRange"] === null || r && r.start === j["nodeTextStart"] + j["textOffset"] && r.end - r.start <= 512 ? j as unknown as StructureJump : null;
}
const textKeys = ["nodeId", "textPreview", "textLength", "truncated", "jump"];
function textPreview(value: unknown, cell = false): StructureTextPreview | null {
  const t = object(value, cell ? [...textKeys, "cellOrder", "row", "column", "rowSpan", "columnSpan", "headerState", "confidence", "triage"] : textKeys);
  if (!t || !id(t["nodeId"]) || !text(t["textPreview"], 512) || !count(t["textLength"], 65536)
    || t["textLength"] < Array.from(t["textPreview"]).length || t["truncated"] !== (t["textLength"] > Array.from(t["textPreview"]).length)) return null;
  const j = jump(t["jump"]);
  return j && j.nodeId === t["nodeId"] && j.normalizedRange && j.normalizedRange.end - j.normalizedRange.start === Math.min(512, t["textLength"])
    ? t as unknown as StructureTextPreview : null;
}
function preview(value: unknown, source: SourceIdentity, nodeId: string, kind: string): boolean {
  const unavailable = object(value, ["kind", "reason"]);
  if (unavailable) return unavailable["kind"] === "unavailable" && one(unavailable["reason"], ["format-has-no-pages", "not-reported", "unsupported-location"]);
  const p = object(value, ["kind", "sourceRevisionId", "objectSha256", "nodeId", "locator", "basis", "scholarlyVerification"]);
  if (!p || p["kind"] !== "source-page-region" || p["sourceRevisionId"] !== source.documentRevisionId || p["objectSha256"] !== source.objectSha256
    || !id(p["nodeId"]) || !one(p["basis"], ["object", "cell"]) || p["scholarlyVerification"] !== "unverified"
    || p["basis"] === "object" && p["nodeId"] !== nodeId || p["basis"] === "cell" && (kind !== "table" || p["nodeId"] === nodeId)) return false;
  const l = object(p["locator"], ["kind", "pageIndex", "x0", "y0", "x1", "y1", "unit", "origin", "frame"]);
  if (!l || l["kind"] !== "page-region" || !count(l["pageIndex"], 499) || l["unit"] !== "points" || l["origin"] !== "top-left" || l["frame"] !== "unrotated-source-page") return false;
  return ["x0", "y0", "x1", "y1"].every(k => typeof l[k] === "number" && Number.isFinite(l[k]) && l[k] >= 0)
    && Number(l["x0"]) <= Number(l["x1"]) && Number(l["y0"]) <= Number(l["y1"]);
}
function entry(value: unknown, source: SourceIdentity, order: number): boolean {
  const e = object(value, ["nodeId", "kind", "order", "jump", "captionState", "captionCount", "captions", "labelCount", "labels",
    "rows", "columns", "gridState", "cellCount", "afterCell", "nextAfterCell", "cells", "confidence", "preview", "retainedPreviewState", "warnings", "excluded", "exclusion"]);
  if (!e || !id(e["nodeId"]) || !one(e["kind"], ["table", "figure"]) || e["order"] !== order || !quality(e["confidence"])
    || !one(e["captionState"], ["reported", "ambiguous", "not-reported", "unavailable"]) || !count(e["captionCount"], 32)
    || !array(e["captions"], 4) || e["captions"].length !== Math.min(4, e["captionCount"]) || !e["captions"].every(v => textPreview(v))
    || !count(e["labelCount"], 16) || !array(e["labels"], 4) || e["labels"].length !== Math.min(4, e["labelCount"]) || !e["labels"].every(v => textPreview(v))
    || !count(e["cellCount"], 10000) || !(e["afterCell"] === null || count(e["afterCell"], 9999)) || !array(e["cells"], 8)
    || !one(e["retainedPreviewState"], ["not-reported", "unavailable"]) || !array(e["warnings"], 32) || !e["warnings"].every(v => text(v, 128))) return false;
  const j = jump(e["jump"]);
  if (!j || j.nodeId !== e["nodeId"] || j.nodeKind !== e["kind"] || !preview(e["preview"], source, e["nodeId"], String(e["kind"]))) return false;
  if (e["kind"] === "table" ? !count(e["rows"], 100000) || !count(e["columns"], 100000) || !one(e["gridState"], ["reported", "ambiguous"])
    : e["rows"] !== null || e["columns"] !== null || e["gridState"] !== null || e["cellCount"] !== 0) return false;
  if (e["captionState"] === "reported" && e["captionCount"] !== 1 || ["not-reported", "unavailable"].includes(String(e["captionState"])) && e["captionCount"] !== 0) return false;
  const start = e["afterCell"] === null ? 0 : Number(e["afterCell"]) + 1, cellCount = Math.min(8, Math.max(0, e["cellCount"] - start));
  if (e["cells"].length !== cellCount || e["nextAfterCell"] !== (cellCount && start + cellCount < e["cellCount"] ? start + cellCount - 1 : null)
    || new Set(e["cells"].map(v => (v as TableCellPreview).nodeId)).size !== cellCount || !e["cells"].every((v, i) => {
      const t = textPreview(v, true); if (!t) return false;
      const c = v as TableCellPreview, q = quality(c.confidence);
      return c.cellOrder === start + i && count(c.row, 100000) && count(c.column, 100000) && count(c.rowSpan, 100000) && c.rowSpan > 0
        && count(c.columnSpan, 100000) && c.columnSpan > 0 && c.row + c.rowSpan <= Number(e["rows"]) && c.column + c.columnSpan <= Number(e["columns"])
        && one(c.headerState, ["reported-header", "reported-body", "not-reported"]) && t.jump.nodeKind === "table-cell" && q !== null
        && c.triage === (q.value === null ? "unknown-confidence" : q.value < 0.8 ? "low-confidence" : "reported-confidence");
    })) return false;
  if (typeof e["excluded"] !== "boolean" || e["excluded"] !== (e["exclusion"] !== null)) return false;
  if (e["exclusion"] !== null) {
    const x = object(e["exclusion"], ["nodeId", "actorId", "commandId", "rationale", "occurredAt"]);
    if (!x || x["nodeId"] !== e["nodeId"] || !id(x["actorId"]) || !id(x["commandId"]) || !text(x["rationale"], 256) || !x["rationale"].trim()
      || typeof x["occurredAt"] !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/u.test(x["occurredAt"]) || !Number.isFinite(Date.parse(x["occurredAt"]))) return false;
  }
  return true;
}
export function decodeTableFigurePage(value: unknown, projectId: string, revisionId: string): TableFigurePage | null {
  try {
    if (!inert(value)) return null;
    const p = object(value, ["schemaVersion", "projectId", "source", "documentRevisionId", "collectionId", "collectionRevisionId", "contentSha256", "structureSha256", "total", "afterOrder", "nextAfterOrder", "entries", "scholarlyVerification"]);
    if (!p || p["schemaVersion"] !== "1.0" || p["projectId"] !== projectId || p["documentRevisionId"] !== revisionId || !id(revisionId)
      || !id(p["collectionId"]) || !id(p["collectionRevisionId"]) || p["collectionId"] === p["collectionRevisionId"] || !sha(p["contentSha256"]) || !sha(p["structureSha256"])
      || !count(p["total"], 1000) || !(p["afterOrder"] === null || count(p["afterOrder"], 999)) || !array(p["entries"], 1) || p["scholarlyVerification"] !== "unverified") return null;
    const source = decodeSourceIdentity(p["source"], projectId), start = p["afterOrder"] === null ? 0 : Number(p["afterOrder"]) + 1;
    if (!source || source.documentRevisionId === revisionId || p["entries"].length !== Math.min(1, Math.max(0, p["total"] - start))
      || p["nextAfterOrder"] !== (p["entries"].length && start + 1 < p["total"] ? start : null)
      || !p["entries"].every(v => entry(v, source, start)) || new TextEncoder().encode(JSON.stringify(p)).length > 65536) return null;
    return p as unknown as TableFigurePage;
  } catch { return null; }
}
export function decodeTableFigureNotice(value: unknown, projectId: string, revisionId: string): TableFigureNotice | null {
  try {
    if (!inert(value)) return null;
    const n = object(value, ["schemaVersion", "projectId", "source", "documentRevisionId", "collectionId", "collectionRevisionId", "status", "reasonCode", "scholarlyVerification"]);
    if (!n || n["schemaVersion"] !== "1.0" || n["projectId"] !== projectId || n["documentRevisionId"] !== revisionId || !id(revisionId)
      || !id(n["collectionId"]) || !id(n["collectionRevisionId"]) || n["collectionId"] === n["collectionRevisionId"] || n["status"] !== "unavailable"
      || !one(n["reasonCode"], ["viewer-resource-limit", "table-figures-unavailable"]) || n["scholarlyVerification"] !== "unverified") return null;
    const source = decodeSourceIdentity(n["source"], projectId);
    return source && source.documentRevisionId !== revisionId ? n as unknown as TableFigureNotice : null;
  } catch { return null; }
}
export interface DocumentTableFigurePort {
  readonly read: (projectId: string, revisionId: string, expected: string | null, afterOrder: number | null, afterCell: number | null, cellObjectId: string | null) => Promise<unknown>;
  readonly enrich: (projectId: string, revisionId: string, commandId: string, expected: string | null) => Promise<unknown>;
  readonly exclude: (projectId: string, revisionId: string, commandId: string, expected: string, nodeId: string, rationale: string) => Promise<unknown>;
}
async function request(command: string, fields: object): Promise<unknown> {
  if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) throw new Error("viewer-source-unavailable");
  return invoke<unknown>(command, { request: { schemaVersion: "1.0", ...fields } });
}
export const nativeDocumentTableFigurePort: DocumentTableFigurePort = {
  read: (projectId, revisionId, expectedCollectionRevisionId, afterOrder, afterCell, cellObjectId) => request("document_reader_table_figures_read", { projectId, revisionId, expectedCollectionRevisionId, afterOrder, afterCell, cellObjectId }),
  enrich: (projectId, revisionId, commandId, expectedCollectionRevisionId) => request("document_reader_table_figures_enrich", { projectId, revisionId, commandId, expectedCollectionRevisionId }),
  exclude: (projectId, revisionId, commandId, expectedCollectionRevisionId, nodeId, rationale) => request("document_reader_table_figures_exclude", { projectId, revisionId, commandId, expectedCollectionRevisionId, nodeId, rationale }),
};
