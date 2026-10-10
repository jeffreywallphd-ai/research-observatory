// Declared synthetic ports and PDF decoder for mounted UI behavior only.
// Native authority, encrypted ranges and the actual PDF worker are separate proofs.
import React from "react";
import { createRoot } from "react-dom/client";
import type { ProjectProjection } from "@research-observatory/contracts/core-api";
import { DocumentViewerWorkspace, type PdfViewer } from "../../../apps/desktop/src/app/DocumentViewerWorkspace";
import { sourceAnchorFixture } from "./anchor-contract";
import { decodeSourceAnchor } from "../../../apps/desktop/src/app/sourceAnchors";
import type { ViewerSelector } from "../../../apps/desktop/src/app/documentViewer";
import type { ReaderAction, ReaderActionPort, ReaderActionRequest } from "../../../apps/desktop/src/app/viewerActions";
import { referenceReaderFixture } from "./reference-reader";
import type { DocumentReferencePort } from "../../../apps/desktop/src/app/documentReferences";
import { citationReaderFixture } from "./citation-reader";
import type { DocumentCitationPort } from "../../../apps/desktop/src/app/documentCitations";
import { tableFigureReaderFixture } from "./table-figure-reader";
import type { DocumentTableFigurePort } from "../../../apps/desktop/src/app/documentTableFigures";
import "../../../packages/ui-tokens/index.css";
import "../../../packages/ui-components/src/styles.css";
import "../../../apps/desktop/src/app.css";

const fixture = decodeSourceAnchor(sourceAnchorFixture(), "00000000-0000-7000-8000-000000000001", "00000000-0000-7000-8000-000000000003")!;
const source = { ...fixture.target.source, format: "pdf" as const };
const revision = fixture.target.revisionId, nodeId = fixture.target.nodeId;
const selection = { projectId: source.projectId, sourceAssertionRevisionId: source.sourceAssertionRevisionId,
  workId: source.workId, workRevisionId: source.workRevisionId, versionId: source.versionId, versionRevisionId: source.versionRevisionId };
const handoff = { attachmentId: source.attachmentId, documentRevisionId: source.documentRevisionId, selection };
const root = createRoot(document.getElementById("root")!);
const state = {
  tableCalls: [] as object[], tableExists: false, staleTables: false, wrongTableSource: false, tableExcluded: false,
  tableExclusion: null as object | null, holdTable: false, unknownTable: false, releaseTable: null as (() => void) | null,
  citationCalls: [] as object[], textCalls: [] as object[], citationExists: false, staleCitations: false,
  wrongCitationSource: false, holdCitation: false, unknownCitation: false, releaseCitation: null as (() => void) | null,
  referenceCalls: [] as object[], referenceExists: false, denyReferences: false, wrongReferenceSource: false,
  referenceMode: "unresolved" as "unresolved" | "exact-linked" | "candidate", holdReference: false,
  releaseReference: null as (() => void) | null, unknownReference: false, staleReferences: false,
  actionCalls: [] as ReaderActionRequest[], actionPermissions: {} as Partial<Record<ReaderAction, boolean>>,
  holdAction: false, unknownAction: false, partialAction: false,
  releaseAction: null as (() => void) | null, activeActions: new Set<string>(),
  anchorMode: false, linkMode: false, linkRevision: revision, noHandoff: false, anchorCalls: 0, denyAnchor: false, wrongAnchorSource: false,
  missingAnchor: false, holdAnchor: false, unknownAnchor: false, releaseAnchor: null as (() => void) | null,
  anchorRotation: 0 as 0 | 90 | 180 | 270, mismatchGeometry: false,
  savedLinks: [] as object[],
  sourceCalls: 0, revisionCalls: 0, closes: 0, rendered: [] as { page: number; scale: number }[], returns: [] as object[],
  denySource: false, substituteSource: false, denyText: false, limitOutline: false, limitText: false,
  holdText: false, releaseText: null as (() => void) | null,
  holdSearch: false, releaseSearch: null as (() => void) | null,
  holdRender: false, releaseRender: null as (() => void) | null,
  mount(active = true): void {
    root.render(<DocumentViewerWorkspace project={{ projectId: source.projectId, open: true } as ProjectProjection}
      handoff={state.noHandoff ? null : { ...handoff, operationId: null, commitRequest: null }} active={active} announce={() => undefined} onReturn={(value) => { state.returns.push(value?.selection ?? selection); state.mount(false); }}
      deepLink={state.linkMode ? { schemaVersion: "1.0", projectId: source.projectId, selector: { attachmentId: source.attachmentId,
        documentRevisionId: source.documentRevisionId, normalizedRevisionId: state.linkRevision }, anchorIds: [fixture.anchorId, secondAnchorId] } : null}
      onRememberLink={(link) => { state.savedLinks.push(link); return true; }}
      port={port} anchors={anchors} anchorPort={anchorPort} outlinePort={outlinePort} textPort={textPort} pdfFactory={pdfFactory} actionPort={actionPort} referencePort={referencePort} citationPort={citationPort} tableFigurePort={tableFigurePort} />);
  },
};
function tablePage(after: number | null, afterCell: number | null = null): object {
  const value = tableFigureReaderFixture() as { entries: Record<string, unknown>[]; collectionId: string; collectionRevisionId: string };
  const entry = value.entries[0]!;
  entry["order"] = after === null ? 0 : 1;
  if (after !== null) Object.assign(entry, { kind: "figure", jump: { ...(entry["jump"] as object), nodeKind: "figure" },
    rows: null, columns: null, gridState: null, cells: [], cellCount: 0 });
  else {
    const cell = (entry["cells"] as Record<string, unknown>[])[0]!;
    const start = afterCell === null ? 0 : afterCell + 1;
    entry["cells"] = Array.from({ length: Math.min(8, 10 - start) }, (_, offset) => {
      const order = start + offset, id = `00000000-0000-7000-8000-${(100 + order).toString().padStart(12, "0")}`;
      return { ...cell, nodeId: id, cellOrder: order, jump: { ...(cell["jump"] as object), nodeId: id }, row: order, column: 0 };
    });
    Object.assign(entry, { cellCount: 10, afterCell, nextAfterCell: start < 8 ? 7 : null });
  }
  const caption = (entry["captions"] as Record<string, unknown>[])[0]!;
  caption["textPreview"] = "Synthetic inert <script>window.tableExecuted=true</script> caption 📚";
  caption["textLength"] = Array.from(caption["textPreview"] as string).length;
  const jump = caption["jump"] as Record<string, unknown>;
  jump["normalizedRange"] = { start: 8, end: 8 + Number(caption["textLength"]) };
  Object.assign(entry, { excluded: state.tableExcluded, exclusion: state.tableExclusion });
  return { ...value, total: 2, afterOrder: after, nextAfterOrder: after === null ? 0 : null,
    source: state.wrongTableSource ? { ...source, workRevisionId: source.attachmentId } : source };
}
const tableFigurePort: DocumentTableFigurePort = {
  read: async (_project, selectedRevision, expected, afterOrder, afterCell, cellObjectId) => {
    state.tableCalls.push({ kind: "read", selectedRevision, expected, afterOrder, afterCell, cellObjectId });
    if (state.holdTable) await new Promise<void>(resolve => { state.releaseTable = resolve; });
    if (state.unknownTable) throw new Error("synthetic-unknown-issued-table");
    if (state.staleTables) {
      const value = tableFigureReaderFixture() as { collectionId: string; collectionRevisionId: string };
      return { schemaVersion: "1.0", projectId: source.projectId, source, documentRevisionId: revision,
        collectionId: value.collectionId, collectionRevisionId: value.collectionRevisionId, status: "unavailable",
        reasonCode: "table-figures-unavailable", scholarlyVerification: "unverified" };
    }
    return state.tableExists ? tablePage(afterOrder, afterCell) : null;
  },
  enrich: async (_project, selectedRevision, command, expected) => {
    state.tableCalls.push({ kind: "enrich", selectedRevision, command, expected }); state.tableExists = true; state.staleTables = false;
    return tablePage(null);
  },
  exclude: async (_project, selectedRevision, command, expected, object, rationale) => {
    state.tableCalls.push({ kind: "exclude", selectedRevision, command, expected, object, rationale });
    state.tableExcluded = true; state.tableExclusion = { nodeId: object, actorId: nodeId, commandId: command, rationale, occurredAt: fixture.createdAt };
    return tablePage(null);
  },
};
function citationPage(after: number | null): object {
  const value = citationReaderFixture() as { entries: Record<string, unknown>[]; collectionId: string; collectionRevisionId: string };
  const entry = value.entries[0]!;
  entry["anchor"] = { ...(entry["anchor"] as object), source };
  entry["order"] = after === null ? 0 : 1;
  const part = entry["paragraph"] as Record<string, unknown>;
  part["textPreview"] = "Synthetic inert <script>window.citationExecuted=true</script> context 📚";
  part["textLength"] = Array.from(part["textPreview"] as string).length;
  part["normalizedRange"] = { start: 0, end: part["textLength"] };
  return { ...value, total: 2, afterOrder: after, nextAfterOrder: after === null ? 0 : null,
    source: state.wrongCitationSource ? { ...source, workRevisionId: source.attachmentId } : source };
}
const citationPort: DocumentCitationPort = {
  read: async (_project, selectedRevision, expected, after) => {
    state.citationCalls.push({ kind: "read", selectedRevision, expected, after });
    if (state.holdCitation) await new Promise<void>(resolve => { state.releaseCitation = resolve; });
    if (state.unknownCitation) throw new Error("synthetic-unknown-issued-citation");
    if (state.staleCitations) {
      const v = citationReaderFixture() as { collectionId: string; collectionRevisionId: string };
      return { schemaVersion: "1.0", projectId: source.projectId, source, documentRevisionId: revision,
        collectionId: v.collectionId, collectionRevisionId: v.collectionRevisionId,
        status: "unavailable", reasonCode: "citations-unavailable", scholarlyVerification: "unverified" };
    }
    return state.citationExists ? citationPage(after) : null;
  },
  enrich: async (_project, selectedRevision, command, reference, expected) => {
    state.citationCalls.push({ kind: "enrich", selectedRevision, command, reference, expected });
    state.citationExists = true; return citationPage(null);
  },
};
const referencePort: DocumentReferencePort = {
  read: async (_project, selectedRevision, expected, after) => {
    state.referenceCalls.push({ kind: "read", selectedRevision, expected, after });
    if (state.holdReference) await new Promise<void>(resolve => { state.releaseReference = resolve; });
    if (state.unknownReference) throw new Error("synthetic-unknown-issued-read");
    if (state.staleReferences) {
      const value = referenceReaderFixture();
      return { schemaVersion: "1.0", projectId: source.projectId, source, documentRevisionId: revision,
        collectionId: value.collectionId, collectionRevisionId: value.collectionRevisionId,
        status: "unavailable", reasonCode: "references-unavailable", scholarlyVerification: "unverified" };
    }
    return !state.referenceExists || state.denyReferences ? null : referencePage();
  },
  enrich: async (_project, selectedRevision, command, expected) => {
    state.referenceCalls.push({ kind: "enrich", selectedRevision, command, expected }); state.referenceExists = true;
    return state.denyReferences ? null : referencePage();
  },
};
function referencePage(): object {
  const value = referenceReaderFixture() as { entries: Record<string, unknown>[] };
  const entry = value.entries[0]!;
  entry["rawPreview"] = "Synthetic inert <script>window.referenceExecuted=true</script> reference 📚";
  entry["rawLength"] = Array.from(entry["rawPreview"] as string).length;
  entry["anchor"] = { ...(entry["anchor"] as object), source };
  if (state.referenceMode === "exact-linked") {
    entry["linkState"] = "exact-linked"; entry["target"] = { workId: source.workId, revisionId: source.workRevisionId };
  }
  if (state.referenceMode === "candidate") {
    entry["linkState"] = "candidate"; entry["candidateCount"] = 1; entry["candidates"] = [{
      target: { workId: source.workId, revisionId: source.workRevisionId }, score: 9200, features: [], flags: [],
      reviewState: "human-review-required", algorithm: "scholarly-duplicate-ranking/1.0.0", featureVersion: "scholarly-duplicate-features/1.0.0",
      configurationSha256: "b3e04c16bcfbb8588a718d55a94217a21a02ba1877fa9ea6ba187ebcdfc98dfc",
    }];
  }
  return { ...value, source: state.wrongReferenceSource ? { ...source, workRevisionId: source.attachmentId } : source };
}
// Explicit interaction doubles, never OS output or Native/Core authority proof.
const actionPolicy = "00000000-0000-7000-8000-000000000024";
const actionPort: ReaderActionPort = {
  request: async request => {
    state.actionCalls.push(request); state.activeActions.add(request.operationId);
    if (state.holdAction) await new Promise<void>(resolve => { state.releaseAction = resolve; });
    if (!state.unknownAction) state.activeActions.delete(request.operationId);
    const base = { schemaVersion: "1.0", projectId: source.projectId, operationId: request.operationId,
      action: request.action, drained: !state.unknownAction, decision: null, review: null };
    if (state.unknownAction) return { ...base, status: "unavailable" };
    const metadata = { source, normalizedRevisionId: request.selector.normalizedRevisionId };
    if (request.stage === "rights-review") {
      if (request.confirmed) state.actionPermissions[request.action] = true;
      return { ...base, status: "recorded", review: { schemaVersion: "1.0", metadata, action: request.action,
        policyRevisionId: actionPolicy, status: "recorded" } };
    }
    if (request.stage === "execute") return { ...base, status: state.actionPermissions[request.action]
      ? state.partialAction ? "partial" : "completed" : "unavailable" };
    const allowed = state.actionPermissions[request.action] === true;
    const denied = request.stage === "denied-attempt";
    const uses = [{ action: "inspect", purpose: "document-analysis", destinationKind: "local-project" }];
    if (request.action !== "open-external-original") uses.push({ action: "derive", purpose: "document-analysis", destinationKind: "local-project" });
    if (["copy-quotation", "print-quotation", "export-quotation"].includes(request.action)) uses.push({ action: "quote", purpose: "viewer-quotation", destinationKind: "local-project" });
    uses.push({ action: "export", purpose: `viewer-${request.action}`, destinationKind: "local-export" });
    return { ...base, status: "policy", decision: { schemaVersion: "1.0", metadata, action: request.action,
      anchorId: request.anchorId, policyRevisionId: actionPolicy, state: denied ? "denied" : allowed ? "ready" : "review-required",
      reasonCode: denied ? "viewer-direct-transfer-disabled" : allowed ? "rights-permitted" : "rights-assertion-missing",
      canReview: !denied && !allowed, selectionLimitCodepoints: 2048,
      requirements: uses.map(use => ({ use: { ...use, provider: null, region: null, shareGroup: null }, code: denied ? "deny" : allowed ? "allow" : "unknown",
        reasonCode: denied ? "viewer-direct-transfer-disabled" : allowed ? "rights-permitted" : "rights-assertion-missing" })) } };
  },
  cancel: async (_project, operation) => !state.activeActions.has(operation),
};
const port = {
  source: async () => { state.sourceCalls += 1; return state.denySource ? null : { source: state.substituteSource
    ? { ...source, workRevisionId: source.attachmentId } : source, normalizedRevisionId: null }; },
  range: async () => null,
};
const anchors = {
  revisions: async () => { state.revisionCalls += 1; return { schemaVersion: "1.0" as const, source, revisions: [{ revisionId: revision, acceptedAt: fixture.createdAt }] }; },
  outline: async () => ({ schemaVersion: "1.0" as const, projectId: source.projectId, documentId: source.documentId, revisionId: revision,
    source, viewKind: "accepted-structured-text" as const, scholarlyVerification: "unverified" as const,
    nodes: [{ nodeId, nodeKind: "paragraph", preview: "Synthetic element", pageNumber: 2, hasText: true,
      selection: { schemaVersion: "1.0" as const, revisionId: revision, nodeId, normalizedRange: { start: 0, end: 16 } } }], nextNodeId: null }),
  list: async () => state.anchorMode ? [fixture.anchorId, secondAnchorId] : [], read: async () => null, create: async () => null,
};
const secondAnchorId = "00000000-0000-7000-8000-000000000022";
const anchorPort = { resolve: async (_project: string, selector: ViewerSelector, anchorId: string) => {
  state.anchorCalls += 1;
  if (state.holdAnchor) await new Promise<void>(resolve => { state.releaseAnchor = resolve; });
  if (state.unknownAnchor) throw new Error("viewer-owned-read-drain-pending");
  if (state.denyAnchor) return null;
  const currentSource = state.wrongAnchorSource ? { ...source, workRevisionId: source.attachmentId } : source;
  const second = anchorId === secondAnchorId;
  const resolvedRevision = selector.normalizedRevisionId ?? revision;
  const pageRegion = { pageIndex: 0, pageNumber: 1, x0: .1, y0: second ? .4 : .2, x1: .8, y1: second ? .5 : .3, sourceWidth: 612, sourceHeight: 792,
    rotation: state.anchorRotation, frame: "unrotated-source-page" as const, origin: "top-left" as const, unit: "normalized" as const, granularity: "block" as const };
  return { schemaVersion: "1.0" as const, anchorId, anchorRevisionId: fixture.anchorRevisionId,
    source: currentSource, metadata: { projectId: source.projectId, documentId: source.documentId, revisionId: resolvedRevision,
      acceptedAt: fixture.createdAt, displayLabel: "Synthetic accepted source", labelOrigin: "canonical-document-revision" as const },
    status: state.missingAnchor ? "missing" as const : "exact" as const, selectorUsed: state.missingAnchor ? "not-resolved" as const : "page-region" as const,
    reason: state.missingAnchor ? "readable-text-not-reported" as const : null, propagation: null,
    target: state.missingAnchor ? null : { ...fixture.target, ...(second ? {
      textPosition: { start: 10, end: 16 }, quote: { exact: "chosen", prefix: "Préface 📚 ", suffix: "" },
      context: { start: 0, text: "Préface 📚 chosen", highlight: { start: 10, end: 16 } },
    } : {}), revisionId: resolvedRevision, source: currentSource, pageRegion, coordinatesState: "available" as const }, scholarlyVerification: "unverified" as const };
} };
const textPort = { text: async (_project: string, _selector: object, _node: string, offset: number) => {
  state.textCalls.push({ node: _node, offset });
  if (state.holdText) await new Promise<void>((resolve) => { state.releaseText = resolve; });
  if (state.limitText) throw new Error("viewer-resource-limit");
  return state.denyText ? null : { metadata: { source, normalizedRevisionId: revision }, nodeId: _node, nodeKind: "paragraph" as const,
    pageNumber: 2, offset, text: "Synthetic inert <script>window.viewerDocumentExecuted=true</script> text", nextOffset: null };
} };
const outlinePort = { outline: async () => {
  if (state.limitOutline) throw new Error("viewer-resource-limit");
  return anchors.outline();
} };
const pdfFactory = (): PdfViewer => ({ open: async () => 3,
  render: async (canvas, page, scale) => {
    if (state.holdRender) await new Promise<void>((resolve) => { state.releaseRender = resolve; });
    state.rendered.push({ page, scale });
    const rotated = !state.mismatchGeometry && (state.anchorRotation === 90 || state.anchorRotation === 270);
    canvas.width = rotated ? 792 : 612; canvas.height = rotated ? 612 : 792;
  },
  thumbnail: async (canvas) => { canvas.width = 96; canvas.height = 128; },
  releaseCanvas: (canvas) => { canvas.width = canvas.height = 0; },
  find: async () => { if (state.holdSearch) await new Promise<void>((resolve) => { state.releaseSearch = resolve; }); return 3; },
  cancelSearch: () => undefined, cancelRender: () => undefined, close: () => { state.closes += 1; },
});
Object.assign(window, { __VIEWER_UI_TEST__: state }); state.mount();
