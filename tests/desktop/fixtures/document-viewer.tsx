// Declared synthetic ports and PDF decoder for mounted UI behavior only.
// Native authority, encrypted ranges and the actual PDF worker are separate proofs.
import React from "react";
import { createRoot } from "react-dom/client";
import type { ProjectProjection } from "@research-observatory/contracts/core-api";
import { DocumentViewerWorkspace, type PdfViewer } from "../../../apps/desktop/src/app/DocumentViewerWorkspace";
import { sourceAnchorFixture } from "./anchor-contract";
import { decodeSourceAnchor } from "../../../apps/desktop/src/app/sourceAnchors";
import type { ViewerSelector } from "../../../apps/desktop/src/app/documentViewer";
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
      port={port} anchors={anchors} anchorPort={anchorPort} outlinePort={outlinePort} textPort={textPort} pdfFactory={pdfFactory} />);
  },
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
  if (state.holdText) await new Promise<void>((resolve) => { state.releaseText = resolve; });
  if (state.limitText) throw new Error("viewer-resource-limit");
  return state.denyText ? null : { metadata: { source, normalizedRevisionId: revision }, nodeId, nodeKind: "paragraph" as const,
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
