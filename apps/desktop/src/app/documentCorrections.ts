import { invoke } from "@tauri-apps/api/core";
import { decodeSourceIdentity, type SourceIdentity } from "./sourceAnchors";
import { viewerSourcesMatch } from "./documentViewer";

export interface CorrectionRegion { readonly kind: "page-region"; readonly pageIndex: number; readonly x0: number; readonly y0: number; readonly x1: number; readonly y1: number; readonly unit: "points"; readonly origin: "top-left"; readonly frame: "unrotated-source-page" }
export type CorrectionLocator = CorrectionRegion | Readonly<{ kind: "text"; projectionId: string; rawRanges: readonly { start: number; end: number }[] }> | Readonly<{ kind: "unavailable"; reason: string }>;
interface NodeCommand { readonly nodeId: string; readonly expectedNodeSha256: string }
export type CorrectionOperation = NodeCommand & (
  { readonly op: "relabel"; readonly label: string } | { readonly op: "reorder"; readonly beforeNodeId: string | null }
  | { readonly op: "split"; readonly at: number } | { readonly op: "merge"; readonly withNodeId: string; readonly expectedWithNodeSha256: string }
  | { readonly op: "reference-rematch"; readonly referenceId: string; readonly expectedReferenceSha256: string; readonly workId: string; readonly workRevisionId: string }
  | { readonly op: "adjust-anchor"; readonly locator: CorrectionRegion } | { readonly op: "exclude" });
export interface CorrectionPatch { readonly schemaVersion: "1.0"; readonly baseRevisionId: string; readonly expectedStructureSha256: string; readonly operations: readonly CorrectionOperation[] }
export interface CorrectionSave { readonly schemaVersion: "1.0"; readonly commandId: string; readonly draftId: string | null; readonly expectedDraftRevisionId: string | null; readonly patch: CorrectionPatch; readonly rationale: string }
export interface CorrectionAccept { readonly schemaVersion: "1.0"; readonly commandId: string; readonly draftRevisionId: string; readonly expectedCurrentRevisionId: string; readonly confirmationSha256: string; readonly decision: "accept-correction" }
export interface CorrectionDiscard { readonly schemaVersion: "1.0"; readonly commandId: string; readonly draftRevisionId: string; readonly confirmationSha256: string; readonly rationale: string }
export type CorrectionCommand = { readonly action: "queue"; readonly afterJobId: string | null } | { readonly action: "page"; readonly revisionId: string; readonly draftRevisionId: string | null; readonly offset: number }
  | { readonly action: "save"; readonly correction: CorrectionSave } | { readonly action: "accept"; readonly acceptance: CorrectionAccept }
  | { readonly action: "discard"; readonly discard: CorrectionDiscard } | { readonly action: "draft" | "impact"; readonly draftRevisionId: string }
  | { readonly action: "targets"; readonly afterWorkId: string | null } | { readonly action: "quality"; readonly jobId: string };
export interface CorrectionDraft {
  readonly schemaVersion: "1.0"; readonly documentType: "document-correction-draft"; readonly correctionVersion: "document-correction-1";
  readonly projectId: string; readonly draftId: string; readonly revisionId: string; readonly previousDraftRevisionId: string | null;
  readonly source: SourceIdentity; readonly patch: CorrectionPatch; readonly rationale: string; readonly authoredBy: string; readonly authoredActorType: "human";
  readonly authoredAt: string; readonly intentRevisionId: string; readonly intentSha256: string; readonly policySha256: string;
  readonly commandId: string; readonly commandKind: "save" | "discard"; readonly commandSha256: string; readonly previewSha256: string; readonly state: "draft" | "discarded";
}
export interface CorrectionDraftView { readonly record: CorrectionDraft; readonly confirmationSha256: string }
export interface CorrectionNode {
  readonly nodeId: string; readonly parentId: string | null; readonly order: number; readonly kind: string; readonly expectedNodeSha256: string | null;
  readonly preview: string; readonly label: string | null; readonly textStart: number | null; readonly textEnd: number | null;
  readonly locator: CorrectionLocator; readonly referenceId: string | null; readonly expectedReferenceSha256: string | null; readonly state: "accepted" | "proposed";
}
export interface HumanReferenceMatch { readonly referenceId: string; readonly workId: string; readonly workRevisionId: string; readonly basis: "human-proposed" | "human-accepted"; readonly scholarlyVerification: "unverified" }
export interface CorrectionPage {
  readonly schemaVersion: "1.0"; readonly projectId: string; readonly source: SourceIdentity; readonly documentId: string; readonly revisionId: string; readonly currentRevisionId: string;
  readonly machineRevisionId: string; readonly attachmentId: string; readonly jobId: string; readonly structureSha256: string;
  readonly acceptedBy: string; readonly acceptedAt: string;
  readonly nodes: readonly CorrectionNode[]; readonly previewNodes: readonly CorrectionNode[]; readonly nextOffset: number | null;
  readonly draft: CorrectionDraftView | null; readonly drafts: readonly { readonly draftRevisionId: string; readonly baseRevisionId: string }[];
  readonly acceptedLabels: readonly { readonly nodeId: string; readonly label: string }[]; readonly acceptedReferenceMatches: readonly HumanReferenceMatch[];
  readonly acceptedDecision: CorrectionDraftView | null; readonly scholarlyVerification: "unverified";
}
export interface CorrectionQueue { readonly schemaVersion: "1.0"; readonly projectId: string; readonly items: readonly { readonly jobId: string; readonly attachmentId: string; readonly revisionId: string | null }[]; readonly nextAfterJobId: string | null }
export interface CorrectionTargets { readonly schemaVersion: "1.0"; readonly projectId: string; readonly items: readonly { readonly workId: string; readonly workRevisionId: string; readonly title: string; readonly scholarlyVerification: "unverified" }[]; readonly nextAfterWorkId: string | null }
export interface CorrectionImpact { readonly schemaVersion: "1.0"; readonly projectId: string; readonly baseRevisionId: string; readonly draftRevisionId: string; readonly graphSha256: string; readonly affectedCount: number; readonly informationalCount: number; readonly legacyUnreportedCount: number; readonly items: readonly { readonly revisionId: string; readonly kind: string; readonly disposition: "stale" | "unknown-impact" | "informational" }[]; readonly truncated: boolean; readonly state: "prospective-rechecked-at-acceptance" }
export interface CorrectionAccepted { readonly schemaVersion: "1.0"; readonly projectId: string; readonly documentId: string; readonly revisionId: string; readonly previousRevisionId: string; readonly structureSha256: string; readonly contentSha256: string; readonly decisionRevisionId: string; readonly acceptedBy: string; readonly acceptedAt: string; readonly scholarlyVerification: "unverified" }
export interface QualityDimension { readonly state: string; readonly [key: string]: string | number | boolean | null | readonly string[] | Readonly<{ state: string; value: number | null }> }
export interface CorrectionQuality { readonly schemaVersion: "1.0"; readonly source: SourceIdentity; readonly jobId: string; readonly assessment: { readonly availability: string; readonly dimensions: Readonly<Record<string, QualityDimension>>; readonly reviewRequired: boolean; readonly reviewReasons: readonly string[]; readonly scholarlyVerification: "unverified" } }
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u;
export const correctionId = (v: unknown): v is string => typeof v === "string" && uuid.test(v);
const sha = (v: unknown): v is string => typeof v === "string" && /^[0-9a-f]{64}$/u.test(v);
const nilId = (v: unknown): boolean => v === null || correctionId(v);
const count = (v: unknown, max = 1_000_000): v is number => typeof v === "number" && Number.isSafeInteger(v) && v >= 0 && v <= max;
const scalarText = (v: unknown, max: number): v is string => typeof v === "string" && v.length <= max * 2 && Array.from(v).length <= max && Array.from(v).every(c => c.length === 2 || c.charCodeAt(0) < 0xd800 || c.charCodeAt(0) > 0xdfff);
const meaningful = (v: unknown, max: number): v is string => scalarText(v,max) && Boolean(v.trim());
const token = (v: unknown): v is string => scalarText(v,128) && /^[A-Za-z0-9][A-Za-z0-9._+-]*$/u.test(v);
const instant = (v: unknown): boolean => typeof v === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/u.test(v) && Number.isFinite(Date.parse(v));
function inert(value: unknown, depth = 0, budget = { left: 12000 }): boolean {
  if (--budget.left < 0 || depth > 18) return false;
  if (value === null || typeof value === "boolean") return true;
  if (typeof value === "number") return Number.isFinite(value);
  if (typeof value === "string") return scalarText(value,65536);
  if (!value || typeof value !== "object" || ![Object.prototype,Array.prototype,null].includes(Object.getPrototypeOf(value))) return false;
  const fields = Object.getOwnPropertyDescriptors(value);
  return Reflect.ownKeys(value).every(k => typeof k === "string" && "value" in fields[k]! && inert(fields[k]!.value,depth+1,budget));
}
function obj(value: unknown, keys: readonly string[]): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const fields = Object.getOwnPropertyDescriptors(value);
  if (Reflect.ownKeys(value).length !== keys.length || keys.some(k => !fields[k] || !("value" in fields[k]!))) return null;
  return Object.fromEntries(keys.map(k => [k,fields[k]!.value]));
}
function list(value: unknown, max: number, check: (v: unknown) => boolean): boolean {
  return Array.isArray(value) && value.length <= max && Reflect.ownKeys(value).length === value.length + 1 && Array.from(value).every(check);
}
function region(v: unknown): boolean {
  const r = obj(v,["kind","pageIndex","x0","y0","x1","y1","unit","origin","frame"]);
  return Boolean(r && r.kind === "page-region" && count(r.pageIndex,499) && r.unit === "points" && r.origin === "top-left" && r.frame === "unrotated-source-page"
    && [r.x0,r.y0,r.x1,r.y1].every(v => typeof v === "number" && Number.isFinite(v) && v >= 0) && Number(r.x1) >= Number(r.x0) && Number(r.y1) >= Number(r.y0));
}
function locator(v: unknown): boolean {
  if (region(v)) return true;
  const t = obj(v,["kind","projectionId","rawRanges"]);
  if (t && t.kind === "text" && token(t.projectionId)) return list(t.rawRanges,10000,v => { const r=obj(v,["start","end"]); return Boolean(r && count(r.start) && count(r.end) && r.start <= r.end); });
  const u=obj(v,["kind","reason"]); return Boolean(u && u.kind === "unavailable" && ["not-reported","format-has-no-pages","unsupported-location","parser-unavailable"].includes(String(u.reason)));
}
function operation(v: unknown): boolean {
  const tag = obj(v,["op","nodeId","expectedNodeSha256"]); // Exclusion has only the shared fields.
  if (tag) return tag.op === "exclude" && correctionId(tag.nodeId) && sha(tag.expectedNodeSha256);
  const fields = { relabel: ["label"], reorder: ["beforeNodeId"], split: ["at"], merge: ["withNodeId","expectedWithNodeSha256"], "reference-rematch": ["referenceId","expectedReferenceSha256","workId","workRevisionId"], "adjust-anchor": ["locator"] } as const;
  if (!v || typeof v !== "object") return false;
  const op=Object.getOwnPropertyDescriptor(v,"op")?.value as keyof typeof fields;
  if (!Object.hasOwn(fields,op)) return false;
  const r=obj(v,["op","nodeId","expectedNodeSha256",...fields[op]]); if (!r || !correctionId(r.nodeId) || !sha(r.expectedNodeSha256)) return false;
  switch (op) { case "relabel": return meaningful(r.label,160); case "reorder": return nilId(r.beforeNodeId); case "split": return count(r.at);
    case "merge": return correctionId(r.withNodeId) && sha(r.expectedWithNodeSha256);
    case "reference-rematch": return correctionId(r.referenceId) && sha(r.expectedReferenceSha256) && correctionId(r.workId) && correctionId(r.workRevisionId);
    case "adjust-anchor": return region(r.locator); }
}
function patch(v: unknown): boolean { const p=obj(v,["schemaVersion","baseRevisionId","expectedStructureSha256","operations"]); return Boolean(p && p.schemaVersion === "1.0" && correctionId(p.baseRevisionId) && sha(p.expectedStructureSha256) && list(p.operations,32,operation)); }
function draft(v: unknown, project: string): boolean {
  const d=obj(v,["schemaVersion","documentType","correctionVersion","projectId","draftId","revisionId","previousDraftRevisionId","source","patch","rationale","authoredBy","authoredActorType","authoredAt","intentRevisionId","intentSha256","policySha256","commandId","commandKind","commandSha256","previewSha256","state"]);
  const source=decodeSourceIdentity(d?.source,project), p=d?.patch as CorrectionPatch | undefined;
  return Boolean(d && source && source.projectId === project && d.projectId === project && d.schemaVersion === "1.0" && d.documentType === "document-correction-draft" && d.correctionVersion === "document-correction-1"
    && [d.draftId,d.revisionId,d.authoredBy,d.intentRevisionId,d.commandId].every(correctionId) && nilId(d.previousDraftRevisionId) && d.revisionId !== d.draftId && d.revisionId !== p?.baseRevisionId && d.revisionId !== source.documentRevisionId
    && patch(p) && meaningful(d.rationale,1000) && d.authoredActorType === "human" && instant(d.authoredAt) && [d.intentSha256,d.policySha256,d.commandSha256,d.previewSha256].every(sha)
    && ["draft","discarded"].includes(String(d.state)) && ["save","discard"].includes(String(d.commandKind)) && (d.state === "discarded") === (d.commandKind === "discard") && (d.state !== "discarded" || correctionId(d.previousDraftRevisionId)));
}
export function decodeCorrectionDraft(v: unknown, project: string): CorrectionDraftView | null {
  try { const r=obj(v,["record","confirmationSha256"]); return inert(v) && r && sha(r.confirmationSha256) && draft(r.record,project) ? v as CorrectionDraftView : null; } catch { return null; }
}
function node(v: unknown, state: string): boolean {
  const n=obj(v,["nodeId","parentId","order","kind","expectedNodeSha256","preview","label","textStart","textEnd","locator","referenceId","expectedReferenceSha256","state"]);
  return Boolean(n && token(n.nodeId) && (n.parentId === null || token(n.parentId)) && count(n.order) && token(n.kind) && scalarText(n.preview,160) && (n.label === null || meaningful(n.label,160)) && locator(n.locator)
    && n.state === state && (state === "accepted" ? correctionId(n.nodeId) && sha(n.expectedNodeSha256) : n.expectedNodeSha256 === null)
    && (n.textStart === null ? n.textEnd === null : count(n.textStart) && count(n.textEnd) && n.textEnd >= n.textStart)
    && (n.referenceId === null ? n.expectedReferenceSha256 === null : correctionId(n.referenceId) && sha(n.expectedReferenceSha256)));
}
export function decodeCorrectionPage(v: unknown, project: string, revision: string): CorrectionPage | null {
  try {
    const p=obj(v,["schemaVersion","projectId","source","documentId","revisionId","currentRevisionId","acceptedBy","acceptedAt","machineRevisionId","attachmentId","jobId","structureSha256","nodes","previewNodes","nextOffset","draft","drafts","acceptedLabels","acceptedReferenceMatches","acceptedDecision","scholarlyVerification"]), source=decodeSourceIdentity(p?.source,project);
    if (!inert(v) || !p || !source || source.projectId !== project || source.attachmentId !== p.attachmentId || source.documentId !== p.documentId || p.projectId !== project || p.schemaVersion !== "1.0" || p.revisionId !== revision || ![p.documentId,p.revisionId,p.currentRevisionId,p.machineRevisionId,p.attachmentId,p.jobId].every(correctionId) || !sha(p.structureSha256) || p.scholarlyVerification !== "unverified"
      || !correctionId(p.acceptedBy) || !instant(p.acceptedAt) || !list(p.nodes,20,v=>node(v,"accepted")) || !list(p.previewNodes,20,v=>node(v,"proposed")) || !(p.nextOffset === null || count(p.nextOffset,9999))
      || (p.draft !== null && (!decodeCorrectionDraft(p.draft,project) || (p.draft as CorrectionDraftView).record.patch.baseRevisionId !== revision || !viewerSourcesMatch((p.draft as CorrectionDraftView).record.source,source)))
      || (p.acceptedDecision !== null && (!decodeCorrectionDraft(p.acceptedDecision,project) || !viewerSourcesMatch((p.acceptedDecision as CorrectionDraftView).record.source,source)))
      || !list(p.drafts,10,v=> { const r=obj(v,["draftRevisionId","baseRevisionId"]); return Boolean(r && correctionId(r.draftRevisionId) && correctionId(r.baseRevisionId)); })
      || !list(p.acceptedLabels,20,v=> { const r=obj(v,["nodeId","label"]); return Boolean(r && correctionId(r.nodeId) && meaningful(r.label,160) && (p.nodes as CorrectionNode[]).some(n=>n.nodeId === r.nodeId)); })
      || !list(p.acceptedReferenceMatches,20,v=> { const r=obj(v,["referenceId","workId","workRevisionId","basis","scholarlyVerification"]); return Boolean(r && [r.referenceId,r.workId,r.workRevisionId].every(correctionId) && r.basis === "human-accepted" && r.scholarlyVerification === "unverified" && (p.nodes as CorrectionNode[]).some(n=>n.referenceId === r.referenceId)); })) return null;
    const nodes=(p.nodes as CorrectionNode[]), previews=(p.previewNodes as CorrectionNode[]);
    if (new Set(nodes.map(n=>n.nodeId)).size !== nodes.length || new Set(previews.map(n=>n.nodeId)).size !== previews.length) return null;
    return v as CorrectionPage;
  } catch { return null; }
}
export function decodeCorrectionQueue(v: unknown, project: string): CorrectionQueue | null {
  try { const q=obj(v,["schemaVersion","projectId","items","nextAfterJobId"]); return inert(v) && q && q.schemaVersion === "1.0" && q.projectId === project && nilId(q.nextAfterJobId) && list(q.items,10,v=> { const r=obj(v,["jobId","attachmentId","revisionId"]); return Boolean(r && correctionId(r.jobId) && correctionId(r.attachmentId) && nilId(r.revisionId)); }) ? v as CorrectionQueue : null; } catch { return null; }
}
export function decodeCorrectionTargets(v: unknown, project: string): CorrectionTargets | null {
  try { const q=obj(v,["schemaVersion","projectId","items","nextAfterWorkId"]); return inert(v) && q && q.schemaVersion === "1.0" && q.projectId === project && nilId(q.nextAfterWorkId) && list(q.items,10,v=> { const r=obj(v,["workId","workRevisionId","title","scholarlyVerification"]); return Boolean(r && correctionId(r.workId) && correctionId(r.workRevisionId) && scalarText(r.title,160) && r.scholarlyVerification === "unverified"); }) ? v as CorrectionTargets : null; } catch { return null; }
}
export function decodeCorrectionImpact(v: unknown, project: string, d: CorrectionDraftView): CorrectionImpact | null {
  try { const p=obj(v,["schemaVersion","projectId","baseRevisionId","draftRevisionId","graphSha256","affectedCount","informationalCount","legacyUnreportedCount","items","truncated","state"]); return inert(v) && p && p.schemaVersion === "1.0" && p.projectId === project && p.baseRevisionId === d.record.patch.baseRevisionId && p.draftRevisionId === d.record.revisionId && sha(p.graphSha256) && [p.affectedCount,p.informationalCount,p.legacyUnreportedCount].every(v=>count(v)) && typeof p.truncated === "boolean" && p.state === "prospective-rechecked-at-acceptance" && list(p.items,20,v=> { const r=obj(v,["revisionId","kind","disposition"]); return Boolean(r && correctionId(r.revisionId) && token(r.kind) && ["stale","unknown-impact","informational"].includes(String(r.disposition))); }) ? v as CorrectionImpact : null; } catch { return null; }
}
export function decodeCorrectionAccepted(v: unknown, project: string, previous: string): CorrectionAccepted | null {
  try { const p=obj(v,["schemaVersion","projectId","documentId","revisionId","previousRevisionId","structureSha256","contentSha256","decisionRevisionId","acceptedBy","acceptedAt","scholarlyVerification"]); return inert(v) && p && p.schemaVersion === "1.0" && p.projectId === project && p.previousRevisionId === previous && [p.documentId,p.revisionId,p.previousRevisionId,p.decisionRevisionId,p.acceptedBy].every(correctionId) && p.revisionId !== previous && sha(p.structureSha256) && sha(p.contentSha256) && instant(p.acceptedAt) && p.scholarlyVerification === "unverified" ? v as CorrectionAccepted : null; } catch { return null; }
}
const dimensionFields: Readonly<Record<string,readonly string[]>> = {
  textCoverage: ["state","basis","observedCount","expectedCount","missingCount","ratio"], pageTextCoverage: ["state","basis","observedCount","expectedCount","missingCount","ratio"],
  encoding: ["state","basis","count"], readingOrder: ["state","warningCount","basis"], sections: ["state","basis","observedCount","expectedCount","missingCount"], references: ["state","basis","observedCount","expectedCount","missingCount"], expectedBlocks: ["state","basis","observedCount","expectedCount","missingCount"],
  anchorCoverage: ["state","basis","observedCount","expectedCount","missingCount","ambiguousCount","parserObservation"], unresolvedReferences: ["state","basis","count"],
  extractionConfidence: ["state","reportedCount","unknownCount","notReportedCount","notApplicableCount","unavailableCount","lowReportedCount","triageThreshold"],
  tableCellConfidence: ["state","reportedCount","unknownCount","notReportedCount","notApplicableCount","unavailableCount","lowReportedCount","triageThreshold"],
  parserTableCellConfidence: ["state","reportedCount","unknownCount","notReportedCount","notApplicableCount","unavailableCount","lowReportedCount","triageThreshold"],
  tableGeometry: ["state","basis","count"], parserWarnings: ["state","count","informationCount","warningCount","errorCount","codes","codesTruncated"],
};
export function decodeCorrectionQuality(v: unknown, project: string, job: string): CorrectionQuality | null {
  try {
    const r=obj(v,["schemaVersion","source","producer","selectionSha256","inputSha256","jobId","attemptId","activityVersion","jobState","diagnosticCode","resultId","resultRevisionId","resultSha256","assessment"]), source=decodeSourceIdentity(r?.source,project);
    const a=obj(r?.assessment,["schemaVersion","definitionVersion","ruleVersion","availability","dimensions","reviewRequired","reviewReasons","humanInspectionAvailable","scholarlyVerification"]), dims=obj(a?.dimensions,Object.keys(dimensionFields));
    const producer=obj(r?.producer,["parserId","version","kind","inputFormats","configurationVersion","configurationSha256","assets"]);
    if (!inert(v) || !r || !source || source.projectId !== project || r.jobId !== job || r.schemaVersion !== "1.0" || r.activityVersion !== "document-parse-1" || !sha(r.selectionSha256) || !sha(r.inputSha256) || !nilId(r.attemptId) || !nilId(r.resultId) || !nilId(r.resultRevisionId) || !(r.resultSha256 === null || sha(r.resultSha256))
      || !a || !dims || a.schemaVersion !== "1.0" || a.definitionVersion !== "parsing-quality-definitions-1" || a.ruleVersion !== "parsing-quality-triage-1" || !["available","not-yet-available","unavailable"].includes(String(a.availability)) || a.humanInspectionAvailable !== true || a.scholarlyVerification !== "unverified" || typeof a.reviewRequired !== "boolean" || !list(a.reviewReasons,16,v=>token(v)) || a.reviewRequired !== Boolean((a.reviewReasons as unknown[]).length)) return null;
    if (!producer || ![producer.parserId,producer.version,producer.configurationVersion].every(token) || !sha(producer.configurationSha256) || !["native","docling-cpu","degraded-inspection"].includes(String(producer.kind))
      || !list(producer.inputFormats,7,v=>typeof v === "string" && ["jats","tei","xml","html","pdf","docx","plain-text"].includes(v)) || !(producer.inputFormats as string[]).includes(source.format)
      || !list(producer.assets,64,v=> {const p=obj(v,["component","version","sha256"]);return Boolean(p && token(p.component) && token(p.version) && sha(p.sha256));})
      || !token(r.jobState) || !(r.diagnosticCode === null || token(r.diagnosticCode))
      || (r.jobState === "succeeded" ? ![r.resultId,r.resultRevisionId,r.attemptId].every(correctionId) || !sha(r.resultSha256) || a.availability !== "available" : r.resultId !== null || r.resultRevisionId !== null || r.resultSha256 !== null || a.availability === "available")) return null;
    for (const [name,fields] of Object.entries(dimensionFields)) {
      const d=obj(dims[name],fields); if (!d || !["reported","unknown","not-reported","not-applicable","unavailable","reported-order","ambiguous"].includes(String(d.state))) return null;
      for (const key of fields.filter(k=>k !== "state")) {
        const value=d[key];
        if (key === "basis") { if (!token(value)) return null; }
        else if (key === "parserObservation") { const p=obj(value,["state","value"]); if (!p || !["reported","unknown","not-reported","not-applicable","unavailable"].includes(String(p.state)) || (p.state === "reported" ? !(typeof p.value === "number" && p.value >= 0 && p.value <= 1) : p.value !== null)) return null; }
        else if (key === "codes") { if (!list(value,32,v=>token(v))) return null; }
        else if (key === "codesTruncated") { if (typeof value !== "boolean") return null; }
        else if (key === "triageThreshold") { if (value !== 0.8) return null; }
        else if (key === "ratio") { if (value !== null && !(typeof value === "number" && value >= 0 && value <= 1)) return null; }
        else if (value !== null && !count(value,Number.MAX_SAFE_INTEGER)) return null;
      }
    }
    return v as CorrectionQuality;
  } catch { return null; }
}
export interface DocumentCorrectionPort { request(project: string, command: CorrectionCommand): Promise<unknown> }
export const nativeDocumentCorrectionPort: DocumentCorrectionPort = {
  async request(projectId,command) {
    if (!("__TAURI_INTERNALS__" in window)) throw new Error("correction-unavailable");
    return invoke("document_correction_request",{ request: { schemaVersion: "1.0",projectId,command } });
  },
};
