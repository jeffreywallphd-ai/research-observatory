// Opaque immutable selectors; renderer text is inert and never Core authority.
export interface CodepointRange { readonly start: number; readonly end: number }
export interface SourceIdentity {
  readonly projectId: string; readonly attachmentId: string; readonly documentId: string; readonly documentRevisionId: string;
  readonly candidateId: string; readonly sourceAssertionRevisionId: string; readonly workId: string; readonly workRevisionId: string;
  readonly versionId: string; readonly versionRevisionId: string; readonly objectSha256: string; readonly byteLength: number;
  readonly format: "jats" | "tei" | "xml" | "html" | "pdf" | "docx" | "plain-text";
  readonly provenance: { readonly kind: "local-import" } | { readonly kind: "remote-acquisition"; readonly locationId: string; readonly receiptSha256: string };
}
export interface AnchorSelection {
  readonly schemaVersion: "1.0"; readonly revisionId: string; readonly nodeId: string;
  readonly normalizedRange: CodepointRange | null;
}
export interface PageRegion {
  readonly pageIndex: number; readonly pageNumber: number; readonly x0: number; readonly y0: number; readonly x1: number; readonly y1: number;
  readonly sourceWidth: number; readonly sourceHeight: number; readonly rotation: 0 | 90 | 180 | 270;
  readonly frame: "unrotated-source-page"; readonly origin: "top-left"; readonly unit: "normalized"; readonly granularity: "block";
}
export interface SourceAnchorTarget {
  readonly schemaVersion: "1.0"; readonly projectId: string; readonly documentId: string; readonly revisionId: string;
  readonly source: SourceIdentity; readonly contentSha256: string; readonly structureSha256: string;
  readonly nodeId: string; readonly nodeKind: string; readonly blockId: string | null; readonly sentenceId: string | null;
  readonly projectionId: string | null; readonly normalizationVersion: "ro-text-nfc-1"; readonly unicodeVersion: "16.0.0";
  readonly textPosition: CodepointRange | null;
  readonly quote: { readonly exact: string; readonly prefix: string; readonly suffix: string } | null;
  readonly context: { readonly start: number; readonly text: string; readonly highlight: CodepointRange } | null;
  readonly pageRegion: PageRegion | null;
  readonly coordinatesState: "available" | "not-reported" | "format-has-no-pages" | "unsupported-location" | "parser-unavailable";
  readonly confidence: { readonly state: "reported" | "unknown" | "not-reported" | "not-applicable" | "unavailable"; readonly value: number | null };
  readonly scholarlyVerification: "unverified";
}
export interface SourceAnchor {
  readonly schemaVersion: "1.0"; readonly anchorId: string; readonly anchorRevisionId: string; readonly createdAt: string;
  readonly target: SourceAnchorTarget;
}
export interface ReaderOutlineNode {
  readonly nodeId: string; readonly nodeKind: string; readonly preview: string; readonly selection: AnchorSelection;
  readonly pageNumber: number | null; readonly hasText: boolean;
}
export interface ReaderOutline {
  readonly schemaVersion: "1.0"; readonly projectId: string; readonly documentId: string; readonly revisionId: string;
  readonly source: SourceIdentity; readonly viewKind: "accepted-structured-text"; readonly scholarlyVerification: "unverified";
  readonly nodes: readonly ReaderOutlineNode[]; readonly nextNodeId: string | null;
}
export interface ReaderRevisions {
  readonly schemaVersion: "1.0"; readonly source: SourceIdentity;
  readonly revisions: readonly { readonly revisionId: string; readonly acceptedAt: string }[];
}

const uuid7 = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u;
const projectUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[47][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u;
const digest = /^[0-9a-f]{64}$/u;
const nodeKinds = ["region", "title", "abstract", "section", "paragraph", "sentence", "list", "list-item", "footnote", "reference", "citation-marker", "table", "table-cell", "figure", "caption", "equation", "unknown"];

function object(value: unknown, keys: readonly string[]): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const descriptors = Object.getOwnPropertyDescriptors(value);
  if (Reflect.ownKeys(value).some((key) => typeof key !== "string" || !("value" in descriptors[key]!))) return null;
  if (Object.keys(descriptors).length !== keys.length || keys.some((key) => !Object.hasOwn(descriptors, key))) return null;
  return Object.fromEntries(Object.entries(descriptors).map(([key, descriptor]) => [key, descriptor.value]));
}
function id(value: unknown): value is string { return typeof value === "string" && uuid7.test(value); }
function nullableId(value: unknown): boolean { return value === null || id(value); }
function count(value: unknown): value is number { return typeof value === "number" && Number.isSafeInteger(value) && value >= 0; }
function sha(value: unknown): value is string { return typeof value === "string" && digest.test(value); }
function instant(value: unknown): value is string {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/u.test(value) && Number.isFinite(Date.parse(value));
}
function text(value: unknown, maximum: number): value is string {
  if (typeof value !== "string") return false;
  const points = Array.from(value);
  return points.length <= maximum && points.every((point) => point.length === 2 || point.charCodeAt(0) < 0xd800 || point.charCodeAt(0) > 0xdfff);
}
function range(value: unknown): CodepointRange | null {
  const item = object(value, ["start", "end"]);
  return item && count(item["start"]) && count(item["end"]) && item["start"] < item["end"]
    ? { start: item["start"], end: item["end"] } : null;
}

export function codepointRangeToUtf16(value: string, selected: CodepointRange): CodepointRange {
  if (!text(value, 8192) || !count(selected.start) || !count(selected.end) || selected.start > selected.end) throw new Error("Invalid passage range");
  const points = Array.from(value);
  if (selected.end > points.length) throw new Error("Invalid passage range");
  return { start: points.slice(0, selected.start).join("").length, end: points.slice(0, selected.end).join("").length };
}

export function decodeSourceIdentity(value: unknown, projectId: string): SourceIdentity | null {
  const item = object(value, ["projectId", "attachmentId", "documentId", "documentRevisionId", "candidateId", "sourceAssertionRevisionId", "workId", "workRevisionId", "versionId", "versionRevisionId", "objectSha256", "byteLength", "format", "provenance"]);
  if (!item || !projectUuid.test(projectId) || item["projectId"] !== projectId
    || ["attachmentId", "documentId", "documentRevisionId", "candidateId", "sourceAssertionRevisionId", "workId", "workRevisionId", "versionId", "versionRevisionId"].some((key) => !id(item[key]))
    || !sha(item["objectSha256"]) || !count(item["byteLength"]) || item["byteLength"] > 128 * 1024 * 1024
    || !["jats", "tei", "xml", "html", "pdf", "docx", "plain-text"].includes(String(item["format"]))) return null;
  const local = object(item["provenance"], ["kind"]);
  const remote = object(item["provenance"], ["kind", "locationId", "receiptSha256"]);
  if (!(local?.["kind"] === "local-import" || remote?.["kind"] === "remote-acquisition" && id(remote["locationId"]) && sha(remote["receiptSha256"]))) return null;
  return item as unknown as SourceIdentity;
}

function pageRegion(value: unknown): PageRegion | null {
  const item = object(value, ["pageIndex", "pageNumber", "x0", "y0", "x1", "y1", "sourceWidth", "sourceHeight", "rotation", "frame", "origin", "unit", "granularity"]);
  if (!item || !count(item["pageIndex"]) || item["pageIndex"] >= 500 || item["pageNumber"] !== item["pageIndex"] + 1
    || ["x0", "y0", "x1", "y1"].some((key) => typeof item[key] !== "number" || !Number.isFinite(item[key]) || item[key] < 0 || item[key] > 1)
    || Number(item["x0"]) > Number(item["x1"]) || Number(item["y0"]) > Number(item["y1"])
    || ["sourceWidth", "sourceHeight"].some((key) => typeof item[key] !== "number" || !Number.isFinite(item[key]) || item[key] <= 0)
    || ![0, 90, 180, 270].includes(Number(item["rotation"])) || typeof item["rotation"] !== "number"
    || item["frame"] !== "unrotated-source-page" || item["origin"] !== "top-left" || item["unit"] !== "normalized" || item["granularity"] !== "block") return null;
  return item as unknown as PageRegion;
}

export function pageRegionPixels(region: PageRegion, width: number, height: number): { x: number; y: number; width: number; height: number } {
  if (!pageRegion(region) || !Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) throw new Error("Invalid page viewport");
  let x = region.x0, y = region.y0;
  let dx = region.x1 - region.x0, dy = region.y1 - region.y0;
  if (region.rotation === 90) [x, y, dx, dy] = [1 - region.y1, region.x0, dy, dx];
  else if (region.rotation === 180) [x, y] = [1 - region.x1, 1 - region.y1];
  else if (region.rotation === 270) [x, y, dx, dy] = [region.y0, 1 - region.x1, dy, dx];
  return { x: x * width, y: y * height, width: dx * width, height: dy * height };
}

export function decodeSourceAnchor(value: unknown, projectId: string, revisionId: string): SourceAnchor | null {
  const receipt = object(value, ["schemaVersion", "anchorId", "anchorRevisionId", "createdAt", "target"]);
  if (!receipt || receipt["schemaVersion"] !== "1.0" || !id(receipt["anchorId"]) || !id(receipt["anchorRevisionId"]) || !instant(receipt["createdAt"])) return null;
  return decodeSourceAnchorTarget(receipt["target"], projectId, revisionId) ? receipt as unknown as SourceAnchor : null;
}

export function decodeSourceAnchorTarget(value: unknown, projectId: string, revisionId: string): SourceAnchorTarget | null {
  const item = object(value, ["schemaVersion", "projectId", "documentId", "revisionId", "source", "contentSha256", "structureSha256", "nodeId", "nodeKind", "blockId", "sentenceId", "projectionId", "normalizationVersion", "unicodeVersion", "textPosition", "quote", "context", "pageRegion", "coordinatesState", "confidence", "scholarlyVerification"]);
  if (!item || item["schemaVersion"] !== "1.0" || item["projectId"] !== projectId || item["revisionId"] !== revisionId || !id(revisionId)
    || !id(item["documentId"]) || !id(item["nodeId"]) || !nodeKinds.includes(String(item["nodeKind"]))
    || !nullableId(item["blockId"]) || !nullableId(item["sentenceId"]) || !nullableId(item["projectionId"])
    || !sha(item["contentSha256"]) || !sha(item["structureSha256"]) || item["normalizationVersion"] !== "ro-text-nfc-1" || item["unicodeVersion"] !== "16.0.0" || item["scholarlyVerification"] !== "unverified") return null;
  const source = decodeSourceIdentity(item["source"], projectId);
  if (!source || source.documentId !== item["documentId"] || source.documentRevisionId === revisionId) return null;
  if ((item["nodeKind"] === "sentence") !== (item["sentenceId"] !== null) || item["sentenceId"] !== null && item["sentenceId"] !== item["nodeId"]) return null;
  const confidence = object(item["confidence"], ["state", "value"]);
  if (!confidence || !["reported", "unknown", "not-reported", "not-applicable", "unavailable"].includes(String(confidence["state"]))
    || (confidence["state"] === "reported" ? typeof confidence["value"] !== "number" || !Number.isFinite(confidence["value"]) || confidence["value"] < 0 || confidence["value"] > 1 : confidence["value"] !== null)) return null;
  if (!["available", "not-reported", "format-has-no-pages", "unsupported-location", "parser-unavailable"].includes(String(item["coordinatesState"]))
    || (item["coordinatesState"] === "available") !== (item["pageRegion"] !== null)
    || item["pageRegion"] !== null && !pageRegion(item["pageRegion"])) return null;
  const parts = [item["projectionId"], item["textPosition"], item["quote"], item["context"]];
  if (parts.some((part) => part === null)) {
    if (!parts.every((part) => part === null)) return null;
  } else {
    const position = range(item["textPosition"]), quote = object(item["quote"], ["exact", "prefix", "suffix"]), context = object(item["context"], ["start", "text", "highlight"]);
    if (!position || !quote || !context || !count(context["start"]) || !text(context["text"], 8192)
      || !text(quote["exact"], 2048) || !quote["exact"] || !text(quote["prefix"], 64) || !text(quote["suffix"], 64)) return null;
    const highlight = range(context["highlight"]), points = Array.from(context["text"]);
    if (!highlight || highlight.end > points.length || position.start !== context["start"] + highlight.start || position.end !== context["start"] + highlight.end
      || points.slice(highlight.start, highlight.end).join("") !== quote["exact"]
      || points.slice(Math.max(0, highlight.start - 64), highlight.start).join("") !== quote["prefix"]
      || points.slice(highlight.end, highlight.end + 64).join("") !== quote["suffix"]) return null;
  }
  return item as unknown as SourceAnchorTarget;
}

export interface SourceDocumentMetadata {
  readonly projectId: string; readonly documentId: string; readonly revisionId: string; readonly acceptedAt: string;
  readonly displayLabel: string; readonly labelOrigin: "canonical-document-revision";
}
export interface AnchorStalePropagation {
  readonly runId: string; readonly state: "completed"; readonly totalItems: number; readonly processedItems: number;
  readonly staleCount: number; readonly unknownCount: number;
}
export interface SourceAnchorResolution {
  readonly schemaVersion: "1.0"; readonly anchorId: string; readonly anchorRevisionId: string;
  readonly source: SourceIdentity; readonly metadata: SourceDocumentMetadata;
  readonly status: "exact" | "fallback" | "missing" | "broken";
  readonly selectorUsed: "page-region" | "structural-text" | "not-resolved";
  readonly reason: "protected-context-unavailable" | "readable-text-not-reported" | null;
  readonly target: SourceAnchorTarget | null; readonly propagation: AnchorStalePropagation | null;
  readonly scholarlyVerification: "unverified";
}
export interface CitationLinkResolution {
  readonly schemaVersion: "1.0"; readonly citationId: string; readonly source: SourceIdentity;
  readonly metadata: SourceDocumentMetadata; readonly marker: SourceAnchorTarget; readonly markerTruncated: boolean;
  readonly resolution: "candidate" | "ambiguous" | "unresolved"; readonly totalCandidates: number;
  readonly targets: readonly { readonly referenceId: string; readonly target: SourceAnchorTarget; readonly previewTruncated: boolean }[];
  readonly nextReferenceId: string | null; readonly scholarlyVerification: "unverified";
}

function sameSource(a: SourceIdentity, b: SourceIdentity): boolean {
  return Object.entries(a).every(([key, value]) => key === "provenance"
    ? Object.entries(a.provenance).length === Object.entries(b.provenance).length
      && Object.entries(a.provenance).every(([k, v]) => Object.entries(b.provenance).some(([other, actual]) => k === other && v === actual))
    : Object.entries(b).some(([other, actual]) => key === other && value === actual));
}
function documentMetadata(value: unknown, source: SourceIdentity, revisionId: string): SourceDocumentMetadata | null {
  const item = object(value, ["projectId", "documentId", "revisionId", "acceptedAt", "displayLabel", "labelOrigin"]);
  return item && item["projectId"] === source.projectId && item["documentId"] === source.documentId
    && item["revisionId"] === revisionId && id(revisionId) && revisionId !== source.documentRevisionId
    && instant(item["acceptedAt"]) && text(item["displayLabel"], 512) && item["labelOrigin"] === "canonical-document-revision"
    ? item as unknown as SourceDocumentMetadata : null;
}

export function decodeAnchorResolution(value: unknown, projectId: string, revisionId: string, anchorId: string): SourceAnchorResolution | null {
  const item = object(value, ["schemaVersion", "anchorId", "anchorRevisionId", "source", "metadata", "status", "selectorUsed", "reason", "target", "propagation", "scholarlyVerification"]);
  const source = decodeSourceIdentity(item?.["source"], projectId);
  if (!item || item["schemaVersion"] !== "1.0" || !id(anchorId) || item["anchorId"] !== anchorId
    || !id(item["anchorRevisionId"]) || !source || !documentMetadata(item["metadata"], source, revisionId)
    || item["scholarlyVerification"] !== "unverified") return null;
  if (item["status"] === "exact" || item["status"] === "fallback") {
    const target = decodeSourceAnchorTarget(item["target"], projectId, revisionId);
    if (!target || !sameSource(source, target.source) || !target.context || item["propagation"] !== null || item["reason"] !== null
      || (item["status"] === "exact" ? item["selectorUsed"] !== "page-region" || target.pageRegion === null
        : item["selectorUsed"] !== "structural-text" || target.pageRegion !== null)) return null;
  } else if (item["status"] === "missing" || item["status"] === "broken") {
    if (item["target"] !== null || item["selectorUsed"] !== "not-resolved") return null;
    if (item["status"] === "missing") {
      if (item["reason"] !== "readable-text-not-reported" || item["propagation"] !== null) return null;
    } else {
      const propagation = object(item["propagation"], ["runId", "state", "totalItems", "processedItems", "staleCount", "unknownCount"]);
      if (item["reason"] !== "protected-context-unavailable" || !propagation || !id(propagation["runId"])
        || propagation["state"] !== "completed" || !count(propagation["totalItems"]) || !count(propagation["processedItems"])
        || !count(propagation["staleCount"]) || !count(propagation["unknownCount"])
        || propagation["totalItems"] !== propagation["processedItems"]
        || propagation["staleCount"] + propagation["unknownCount"] > propagation["processedItems"]) return null;
    }
  } else return null;
  return item as unknown as SourceAnchorResolution;
}

export function decodeCitationLinks(value: unknown, projectId: string, revisionId: string, citationId: string): CitationLinkResolution | null {
  const item = object(value, ["schemaVersion", "citationId", "source", "metadata", "marker", "markerTruncated", "resolution", "totalCandidates", "targets", "nextReferenceId", "scholarlyVerification"]);
  const source = decodeSourceIdentity(item?.["source"], projectId);
  const marker = decodeSourceAnchorTarget(item?.["marker"], projectId, revisionId);
  if (!item || item["schemaVersion"] !== "1.0" || !id(citationId) || item["citationId"] !== citationId || !source || !marker
    || !sameSource(source, marker.source) || !documentMetadata(item["metadata"], source, revisionId)
    || typeof item["markerTruncated"] !== "boolean" || item["scholarlyVerification"] !== "unverified"
    || !count(item["totalCandidates"]) || !Array.isArray(item["targets"]) || item["targets"].length > 2
    || item["targets"].length > item["totalCandidates"] || !nullableId(item["nextReferenceId"])) return null;
  const total = item["totalCandidates"];
  if (item["resolution"] === "unresolved" ? total !== 0 : item["resolution"] === "candidate" ? total !== 1
    : item["resolution"] === "ambiguous" ? total < 2 : true) return null;
  const identities = new Set<string>();
  for (const value of item["targets"]) {
    const row = object(value, ["referenceId", "target", "previewTruncated"]);
    const target = decodeSourceAnchorTarget(row?.["target"], projectId, revisionId);
    if (!row || !id(row["referenceId"]) || identities.has(row["referenceId"]) || !target || !sameSource(source, target.source)
      || typeof row["previewTruncated"] !== "boolean") return null;
    identities.add(row["referenceId"]);
  }
  if (item["nextReferenceId"] !== null && (item["targets"].length === 0 || total <= item["targets"].length
    || item["nextReferenceId"] !== item["targets"].at(-1)["referenceId"])) return null;
  return item as unknown as CitationLinkResolution;
}

export function decodeReaderRevisions(value: unknown, projectId: string, attachmentId: string): ReaderRevisions | null {
  const item = object(value, ["schemaVersion", "source", "revisions"]), source = decodeSourceIdentity(item?.["source"], projectId);
  if (!item || item["schemaVersion"] !== "1.0" || !source || source.attachmentId !== attachmentId || !Array.isArray(item["revisions"]) || item["revisions"].length > 100) return null;
  const ids = new Set<string>();
  for (const value of item["revisions"]) {
    const revision = object(value, ["revisionId", "acceptedAt"]);
    if (!revision || !id(revision["revisionId"]) || !instant(revision["acceptedAt"]) || ids.has(revision["revisionId"])) return null;
    ids.add(revision["revisionId"]);
  }
  return item as unknown as ReaderRevisions;
}

export function decodeReaderOutline(value: unknown, projectId: string, revisionId: string): ReaderOutline | null {
  const item = object(value, ["schemaVersion", "projectId", "documentId", "revisionId", "source", "viewKind", "scholarlyVerification", "nodes", "nextNodeId"]);
  const source = decodeSourceIdentity(item?.["source"], projectId);
  if (!item || item["schemaVersion"] !== "1.0" || item["projectId"] !== projectId || item["revisionId"] !== revisionId || !source || item["documentId"] !== source.documentId
    || item["viewKind"] !== "accepted-structured-text" || item["scholarlyVerification"] !== "unverified" || !nullableId(item["nextNodeId"]) || !Array.isArray(item["nodes"]) || item["nodes"].length > 50) return null;
  const ids = new Set<string>();
  for (const value of item["nodes"]) {
    const node = object(value, ["nodeId", "nodeKind", "preview", "selection", "pageNumber", "hasText"]);
    const selection = object(node?.["selection"], ["schemaVersion", "revisionId", "nodeId", "normalizedRange"]);
    if (!node || !id(node["nodeId"]) || ids.has(node["nodeId"]) || !nodeKinds.includes(String(node["nodeKind"])) || !text(node["preview"], 160)
      || typeof node["hasText"] !== "boolean" || node["pageNumber"] !== null && (!count(node["pageNumber"]) || node["pageNumber"] < 1 || node["pageNumber"] > 500)
      || !selection || selection["schemaVersion"] !== "1.0" || selection["revisionId"] !== revisionId || selection["nodeId"] !== node["nodeId"]
      || (selection["normalizedRange"] !== null && !range(selection["normalizedRange"])) || node["hasText"] !== (selection["normalizedRange"] !== null)) return null;
    ids.add(node["nodeId"]);
  }
  if (item["nextNodeId"] !== null && !ids.has(String(item["nextNodeId"]))) return null;
  return item as unknown as ReaderOutline;
}

export function decodeAnchorIds(value: unknown): readonly string[] | null {
  const item = object(value, ["anchorIds"]);
  return item && Array.isArray(item["anchorIds"]) && item["anchorIds"].length <= 100 && item["anchorIds"].every(id)
    && new Set(item["anchorIds"]).size === item["anchorIds"].length ? item["anchorIds"] : null;
}
