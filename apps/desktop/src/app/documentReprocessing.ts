import { invoke } from "@tauri-apps/api/core";
import { decodeSourceIdentity, type SourceIdentity } from "./sourceAnchors";
import type { CorrectionLocator } from "./documentCorrections";

export type ReprocessingCommand =
  | { readonly action: "queue"; readonly afterBatchId: string | null }
  | { readonly action: "create"; readonly batch: { readonly schemaVersion: "1.0"; readonly commandId: string; readonly baseRevisionIds: readonly string[] } }
  | { readonly action: "read"; readonly batchRevisionId: string }
  | { readonly action: "read-impact"; readonly batchRevisionId: string; readonly itemId: string }
  | { readonly action: "compare"; readonly batchRevisionId: string; readonly itemId: string; readonly offset: number }
  | { readonly action: "reconcile"; readonly reconciliation: { readonly schemaVersion: "1.0"; readonly commandId: string; readonly comparisonRevisionId: string; readonly expectedPlanRevisionId: string | null; readonly rationale: string; readonly mappings: readonly ReprocessingMapping[] } }
  | { readonly action: "accept"; readonly acceptance: { readonly schemaVersion: "1.0"; readonly commandId: string; readonly planRevisionId: string; readonly expectedCurrentRevisionId: string; readonly confirmationSha256: string; readonly expectedGraphSha256: string; readonly decision: "accept-reparse" } }
  | { readonly action: "continue"; readonly continuation: { readonly schemaVersion: "1.0"; readonly commandId: string; readonly batchRevisionId: string; readonly itemId: string; readonly expectedJobId: string | null } }
  | { readonly action: "cancel"; readonly cancellation: { readonly schemaVersion: "1.0"; readonly commandId: string; readonly batchRevisionId: string } }
  | { readonly action: "resume-impact"; readonly batchRevisionId: string; readonly itemId: string; readonly expectedCheckpointSha256: string };
export interface ReprocessingMapping { readonly obligationId: string; readonly nodeId: string; readonly relatedNodeId: string | null; readonly referenceId: string | null }
export interface ReprocessingItem { readonly itemId: string; readonly baseRevisionId: string; readonly jobId: string | null; readonly state: "not-submitted" | "processing" | "needs-continuation" | "failed" | "cancelled" | "ready" | "base-conflict" | "accepted"; readonly acceptedRevisionId: string | null }
export interface ReprocessingBatch { readonly schemaVersion: "1.0"; readonly projectId: string; readonly batchId: string; readonly batchRevisionId: string; readonly state: "active" | "cancelled"; readonly items: readonly ReprocessingItem[] }
export interface ReprocessingQueue { readonly schemaVersion: "1.0"; readonly projectId: string; readonly items: readonly ReprocessingBatch[]; readonly nextAfterBatchId: string | null }
export type DifferenceState = "unchanged" | "moved" | "modified" | "added" | "removed" | "ambiguous" | "unresolvable";
export interface ReprocessingDifference { readonly kind: "node" | "reference" | "anchor"; readonly oldId: string | null; readonly newId: string | null; readonly state: DifferenceState; readonly oldPreview: string | null; readonly newPreview: string | null; readonly oldLocator: CorrectionLocator | null; readonly newLocator: CorrectionLocator | null }
export type ReprocessingCounts = Readonly<Record<DifferenceState, number>>;
export interface ReprocessingObligation { readonly obligationId: string; readonly originalDraftRevisionId: string; readonly originalBaseRevisionId: string; readonly operationIndex: number; readonly operation: string; readonly oldNodeId: string; readonly oldNodeSha256: string; readonly oldPreview: string; readonly relatedOldNodeId: string | null; readonly originalReferenceId: string | null; readonly originalAuthor: string; readonly originalRationale: string }
export interface ReprocessingNode { readonly nodeId: string; readonly parentId: string | null; readonly order: number; readonly kind: string; readonly preview: string; readonly nodeSha256: string; readonly referenceId: string | null }
export interface ReprocessingAssessment { readonly schemaVersion: "1.0"; readonly definitionVersion: "parsing-quality-definitions-1"; readonly ruleVersion: "parsing-quality-triage-1"; readonly availability: "available" | "not-yet-available" | "unavailable"; readonly dimensions: Readonly<Record<string, Readonly<Record<string, unknown>>>>; readonly reviewRequired: boolean; readonly reviewReasons: readonly string[]; readonly humanInspectionAvailable: true; readonly scholarlyVerification: "unverified" }
export interface ReprocessingPage {
  readonly schemaVersion: "1.0"; readonly projectId: string; readonly batchId: string; readonly batchRevisionId: string; readonly itemId: string; readonly baseRevisionId: string; readonly currentRevisionId: string;
  readonly source: SourceIdentity; readonly jobId: string; readonly attemptId: string; readonly resultId: string; readonly comparisonRevisionId: string; readonly candidateRevisionId: string;
  readonly planRevisionId: string | null; readonly confirmationSha256: string | null; readonly generation: number; readonly generationCount: number; readonly totalObligations: number; readonly unresolvedCount: number;
  readonly obligations: readonly ReprocessingObligation[]; readonly candidateNodes: readonly ReprocessingNode[]; readonly differences: readonly ReprocessingDifference[]; readonly differenceCounts: ReprocessingCounts;
  readonly anchorCandidates: readonly ReprocessingDifference[]; readonly anchorCounts: ReprocessingCounts; readonly nextOffset: number | null; readonly oldQuality: ReprocessingAssessment; readonly newQuality: ReprocessingAssessment;
  readonly impact: { readonly graphSha256: string; readonly affectedCount: number; readonly informationalCount: number; readonly legacyUnreportedCount: number; readonly state: "prospective-rechecked-at-acceptance" };
  readonly state: "review" | "ready-to-accept" | "base-conflict"; readonly scholarlyVerification: "unverified";
}
export interface ReprocessingAccepted { readonly schemaVersion: "1.0"; readonly projectId: string; readonly batchId: string; readonly batchRevisionId: string; readonly itemId: string; readonly previousRevisionId: string; readonly revisionId: string; readonly machineRevisionId: string; readonly impactRunId: string; readonly impactState: "running" | "completed" | "cancelled"; readonly impactCheckpointSha256: string; readonly processedItems: number; readonly totalItems: number; readonly scholarlyVerification: "unverified" }

const states: readonly DifferenceState[] = ["unchanged","moved","modified","added","removed","ambiguous","unresolvable"];
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u;
const id = (value: unknown): value is string => typeof value === "string" && uuid.test(value);
const nilId = (value: unknown): boolean => value === null || id(value);
const sha = (value: unknown): value is string => typeof value === "string" && /^[0-9a-f]{64}$/u.test(value);
const count = (value: unknown, max = 100000): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= max;
function text(value: unknown, max: number): value is string { return typeof value === "string" && Array.from(value).length <= max && Array.from(value).every(point=>point.length === 2 || point.charCodeAt(0) < 0xd800 || point.charCodeAt(0) > 0xdfff); }
const token = (value: unknown): value is string => text(value,128) && /^[A-Za-z0-9][A-Za-z0-9._+-]*$/u.test(value);
function inert(value: unknown, depth=0, budget={left:12000}): boolean {
  if (--budget.left < 0 || depth > 18) return false;
  if (value === null || typeof value === "boolean") return true;
  if (typeof value === "number") return Number.isFinite(value);
  if (typeof value === "string") return text(value,65536);
  if (!value || typeof value !== "object" || ![Object.prototype,Array.prototype,null].includes(Object.getPrototypeOf(value))) return false;
  const fields=Object.getOwnPropertyDescriptors(value);
  return Reflect.ownKeys(value).every(key=>typeof key === "string" && "value" in fields[key]! && inert(fields[key]!.value,depth+1,budget));
}
function obj(value: unknown, keys: readonly string[]): Record<string,unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const fields=Object.getOwnPropertyDescriptors(value);
  if (Reflect.ownKeys(value).length !== keys.length || keys.some(key=>!fields[key] || !("value" in fields[key]!))) return null;
  return Object.fromEntries(keys.map(key=>[key,fields[key]!.value]));
}
function list(value: unknown, max: number, check: (item: unknown)=>boolean): boolean { return Array.isArray(value) && value.length <= max && Reflect.ownKeys(value).length === value.length+1 && Array.from(value).every(check); }
function unique(value: readonly { readonly nodeId: string }[]): boolean { return new Set(value.map(item=>item.nodeId)).size === value.length; }
function locator(value: unknown): boolean {
  const region=obj(value,["kind","pageIndex","x0","y0","x1","y1","unit","origin","frame"]);
  if (region) return region.kind === "page-region" && count(region.pageIndex,499) && region.unit === "points" && region.origin === "top-left" && region.frame === "unrotated-source-page" && [region.x0,region.y0,region.x1,region.y1].every(v=>typeof v === "number" && Number.isFinite(v) && v >= 0) && Number(region.x1) >= Number(region.x0) && Number(region.y1) >= Number(region.y0);
  const span=obj(value,["kind","projectionId","rawRanges"]);
  if (span) return span.kind === "text" && token(span.projectionId) && list(span.rawRanges,10000,v=> {const r=obj(v,["start","end"]);return Boolean(r && count(r.start,Number.MAX_SAFE_INTEGER) && count(r.end,Number.MAX_SAFE_INTEGER) && r.end >= r.start);});
  const unavailable=obj(value,["kind","reason"]);
  return Boolean(unavailable && unavailable.kind === "unavailable" && ["not-reported","format-has-no-pages","unsupported-location","parser-unavailable"].includes(String(unavailable.reason)));
}
function difference(value: unknown): boolean {
  const d=obj(value,["kind","oldId","newId","state","oldPreview","newPreview","oldLocator","newLocator"]);
  return Boolean(d && ["node","reference","anchor"].includes(String(d.kind)) && [d.oldId,d.newId].every(v=>v === null || token(v)) && states.includes(d.state as DifferenceState) && [d.oldPreview,d.newPreview].every(v=>v === null || text(v,160)) && [d.oldLocator,d.newLocator].every(v=>v === null || locator(v)));
}
function counts(value: unknown): boolean { const d=obj(value,states);return Boolean(d && Object.values(d).every(v=>count(v))); }
const dimensions: Readonly<Record<string,readonly string[]>> = {
  textCoverage:["state","basis","observedCount","expectedCount","missingCount","ratio"],pageTextCoverage:["state","basis","observedCount","expectedCount","missingCount","ratio"],
  encoding:["state","basis","count"],readingOrder:["state","warningCount","basis"],sections:["state","basis","observedCount","expectedCount","missingCount"],references:["state","basis","observedCount","expectedCount","missingCount"],expectedBlocks:["state","basis","observedCount","expectedCount","missingCount"],
  anchorCoverage:["state","basis","observedCount","expectedCount","missingCount","ambiguousCount","parserObservation"],unresolvedReferences:["state","basis","count"],
  extractionConfidence:["state","reportedCount","unknownCount","notReportedCount","notApplicableCount","unavailableCount","lowReportedCount","triageThreshold"],tableCellConfidence:["state","reportedCount","unknownCount","notReportedCount","notApplicableCount","unavailableCount","lowReportedCount","triageThreshold"],parserTableCellConfidence:["state","reportedCount","unknownCount","notReportedCount","notApplicableCount","unavailableCount","lowReportedCount","triageThreshold"],
  tableGeometry:["state","basis","count"],parserWarnings:["state","count","informationCount","warningCount","errorCount","codes","codesTruncated"],
};
function assessment(value: unknown): boolean {
  const a=obj(value,["schemaVersion","definitionVersion","ruleVersion","availability","dimensions","reviewRequired","reviewReasons","humanInspectionAvailable","scholarlyVerification"]), ds=obj(a?.dimensions,Object.keys(dimensions));
  if (!a || !ds || a.schemaVersion !== "1.0" || a.definitionVersion !== "parsing-quality-definitions-1" || a.ruleVersion !== "parsing-quality-triage-1" || !["available","not-yet-available","unavailable"].includes(String(a.availability)) || a.humanInspectionAvailable !== true || a.scholarlyVerification !== "unverified" || typeof a.reviewRequired !== "boolean" || !list(a.reviewReasons,16,token) || a.reviewRequired !== Boolean((a.reviewReasons as unknown[]).length)) return false;
  for (const [name,fields] of Object.entries(dimensions)) {
    const d=obj(ds[name],fields);if (!d || !["reported","unknown","not-reported","not-applicable","unavailable","reported-order","ambiguous"].includes(String(d.state))) return false;
    for (const key of fields.filter(k=>k !== "state")) {
      const v=d[key];
      if (key === "basis") { if (!token(v)) return false; }
      else if (key === "parserObservation") {const p=obj(v,["state","value"]);if (!p || !["reported","unknown","not-reported","not-applicable","unavailable"].includes(String(p.state)) || (p.state === "reported" ? !(typeof p.value === "number" && p.value >= 0 && p.value <= 1) : p.value !== null)) return false;}
      else if (key === "codes") {if (!list(v,32,token)) return false;}
      else if (key === "codesTruncated") {if (typeof v !== "boolean") return false;}
      else if (key === "triageThreshold") {if (v !== 0.8) return false;}
      else if (key === "ratio") {if (v !== null && !(typeof v === "number" && v >= 0 && v <= 1)) return false;}
      else if (v !== null && !count(v,Number.MAX_SAFE_INTEGER)) return false;
    }
  }
  return true;
}
function batch(value: unknown, project: string): boolean {
  const b=obj(value,["schemaVersion","projectId","batchId","batchRevisionId","state","items"]);
  if (!b || b.schemaVersion !== "1.0" || b.projectId !== project || !id(b.batchId) || !id(b.batchRevisionId) || !["active","cancelled"].includes(String(b.state)) || !list(b.items,10,v=> {const i=obj(v,["itemId","baseRevisionId","jobId","state","acceptedRevisionId"]);return Boolean(i && id(i.itemId) && id(i.baseRevisionId) && nilId(i.jobId) && nilId(i.acceptedRevisionId) && ["not-submitted","processing","needs-continuation","failed","cancelled","ready","base-conflict","accepted"].includes(String(i.state)) && (i.state === "accepted") === (i.acceptedRevisionId !== null));})) return false;
  const items=b.items as ReprocessingItem[];
  return new Set(items.map(item=>item.itemId)).size === items.length && new Set(items.map(item=>item.baseRevisionId)).size === items.length;
}
export function decodeReprocessingBatch(value: unknown, project: string): ReprocessingBatch | null {try {return inert(value) && batch(value,project) ? value as ReprocessingBatch : null;} catch {return null;} }
export function decodeReprocessingQueue(value: unknown, project: string): ReprocessingQueue | null {try {const q=obj(value,["schemaVersion","projectId","items","nextAfterBatchId"]);return inert(value) && q && q.schemaVersion === "1.0" && q.projectId === project && nilId(q.nextAfterBatchId) && list(q.items,10,v=>batch(v,project)) && new Set((q.items as ReprocessingBatch[]).map(b=>b.batchId)).size === (q.items as ReprocessingBatch[]).length ? value as ReprocessingQueue : null;} catch {return null;} }
export function decodeReprocessingPage(value: unknown, project: string, batchRevision: string, item: string): ReprocessingPage | null {
  try {
    if (!inert(value)) return null;
    const p=obj(value,["schemaVersion","projectId","batchId","batchRevisionId","itemId","baseRevisionId","currentRevisionId","source","jobId","attemptId","resultId","comparisonRevisionId","candidateRevisionId","planRevisionId","confirmationSha256","generation","generationCount","totalObligations","unresolvedCount","obligations","candidateNodes","differences","differenceCounts","anchorCandidates","anchorCounts","nextOffset","oldQuality","newQuality","impact","state","scholarlyVerification"]), source=decodeSourceIdentity(p?.source,project);
    const impact=obj(p?.impact,["graphSha256","affectedCount","informationalCount","legacyUnreportedCount","state"]);
    if (!p || !source || p.schemaVersion !== "1.0" || p.projectId !== project || p.batchRevisionId !== batchRevision || p.itemId !== item || ![p.batchId,p.batchRevisionId,p.itemId,p.baseRevisionId,p.currentRevisionId,p.jobId,p.attemptId,p.resultId,p.comparisonRevisionId,p.candidateRevisionId].every(id) || !nilId(p.planRevisionId) || !(p.confirmationSha256 === null || sha(p.confirmationSha256)) || (p.planRevisionId === null) !== (p.confirmationSha256 === null) || ![p.generation,p.generationCount,p.totalObligations,p.unresolvedCount].every(v=>count(v)) || Number(p.generation) > Number(p.generationCount) || Number(p.unresolvedCount) > Number(p.totalObligations) || p.scholarlyVerification !== "unverified" || !["review","ready-to-accept","base-conflict"].includes(String(p.state)) || (p.state === "ready-to-accept" && (p.unresolvedCount !== 0 || p.planRevisionId === null || p.currentRevisionId !== p.baseRevisionId)) || !(p.nextOffset === null || count(p.nextOffset)) || !assessment(p.oldQuality) || !assessment(p.newQuality) || !counts(p.differenceCounts) || !counts(p.anchorCounts) || !list(p.differences,20,difference) || !list(p.anchorCandidates,20,difference) || !impact || !sha(impact.graphSha256) || ![impact.affectedCount,impact.informationalCount,impact.legacyUnreportedCount].every(v=>count(v)) || impact.state !== "prospective-rechecked-at-acceptance") return null;
    if (!list(p.obligations,32,v=> {const o=obj(v,["obligationId","originalDraftRevisionId","originalBaseRevisionId","operationIndex","operation","oldNodeId","oldNodeSha256","oldPreview","relatedOldNodeId","originalReferenceId","originalAuthor","originalRationale"]);return Boolean(o && sha(o.obligationId) && [o.originalDraftRevisionId,o.originalBaseRevisionId,o.oldNodeId,o.originalAuthor].every(id) && sha(o.oldNodeSha256) && count(o.operationIndex,31) && ["relabel","reorder","split","merge","reference-rematch","adjust-anchor","exclude"].includes(String(o.operation)) && text(o.oldPreview,160) && text(o.originalRationale,160) && nilId(o.relatedOldNodeId) && nilId(o.originalReferenceId));}) || !list(p.candidateNodes,20,v=> {const n=obj(v,["nodeId","parentId","order","kind","preview","nodeSha256","referenceId"]);return Boolean(n && id(n.nodeId) && nilId(n.parentId) && count(n.order) && token(n.kind) && text(n.preview,160) && sha(n.nodeSha256) && nilId(n.referenceId));}) || !unique(p.candidateNodes as ReprocessingNode[]) || new Set((p.obligations as ReprocessingObligation[]).map(o=>o.obligationId)).size !== (p.obligations as ReprocessingObligation[]).length) return null;
    return value as ReprocessingPage;
  } catch {return null;}
}
export function decodeReprocessingAccepted(value: unknown, project: string, batchRevision: string | null, item: string): ReprocessingAccepted | null {
  try {const a=obj(value,["schemaVersion","projectId","batchId","batchRevisionId","itemId","previousRevisionId","revisionId","machineRevisionId","impactRunId","impactState","impactCheckpointSha256","processedItems","totalItems","scholarlyVerification"]);return inert(value) && a && a.schemaVersion === "1.0" && a.projectId === project && (batchRevision === null || a.batchRevisionId === batchRevision) && a.itemId === item && [a.batchId,a.batchRevisionId,a.itemId,a.previousRevisionId,a.revisionId,a.machineRevisionId,a.impactRunId].every(id) && a.previousRevisionId !== a.revisionId && sha(a.impactCheckpointSha256) && ["running","completed","cancelled"].includes(String(a.impactState)) && count(a.processedItems) && count(a.totalItems) && a.processedItems <= a.totalItems && a.scholarlyVerification === "unverified" ? value as ReprocessingAccepted : null;} catch {return null;}
}
export interface DocumentReprocessingPort { request(project: string, command: ReprocessingCommand): Promise<unknown> }
export const nativeDocumentReprocessingPort: DocumentReprocessingPort = {async request(projectId,command) {if (!("__TAURI_INTERNALS__" in window)) throw new Error("reprocessing-unavailable");return invoke("document_reprocessing_request",{request:{schemaVersion:"1.0",projectId,command}});} };
