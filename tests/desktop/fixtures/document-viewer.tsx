// Declared synthetic ports and PDF decoder for mounted UI behavior only.
// Native authority, encrypted ranges and the actual PDF worker are separate proofs.
import React from "react";
import { createRoot } from "react-dom/client";
import type { ProjectProjection } from "@research-observatory/contracts/core-api";
import { DocumentViewerWorkspace, type PdfViewer } from "../../../apps/desktop/src/app/DocumentViewerWorkspace";
import { sourceAnchorFixture } from "./anchor-contract";
import { decodeSourceAnchor } from "../../../apps/desktop/src/app/sourceAnchors";
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
  sourceCalls: 0, revisionCalls: 0, closes: 0, rendered: [] as { page: number; scale: number }[], returns: [] as object[],
  denySource: false, substituteSource: false, denyText: false, holdText: false, releaseText: null as (() => void) | null,
  holdSearch: false, releaseSearch: null as (() => void) | null,
  holdRender: false, releaseRender: null as (() => void) | null,
  mount(active = true): void {
    root.render(<DocumentViewerWorkspace project={{ projectId: source.projectId, open: true } as ProjectProjection}
      handoff={handoff} active={active} announce={() => undefined} onReturn={() => { state.returns.push(selection); state.mount(false); }}
      port={port} anchors={anchors} textPort={textPort} pdfFactory={pdfFactory} />);
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
  list: async () => [], read: async () => null, create: async () => null,
};
const textPort = { text: async (_project: string, _selector: object, _node: string, offset: number) => {
  if (state.holdText) await new Promise<void>((resolve) => { state.releaseText = resolve; });
  return state.denyText ? null : { metadata: { source, normalizedRevisionId: revision }, nodeId, nodeKind: "paragraph" as const,
    pageNumber: 2, offset, text: "Synthetic inert <script>window.viewerDocumentExecuted=true</script> text", nextOffset: null };
} };
const pdfFactory = (): PdfViewer => ({ open: async () => 3,
  render: async (canvas, page, scale) => {
    if (state.holdRender) await new Promise<void>((resolve) => { state.releaseRender = resolve; });
    state.rendered.push({ page, scale }); canvas.width = 612; canvas.height = 792;
  },
  thumbnail: async (canvas) => { canvas.width = 96; canvas.height = 128; },
  releaseCanvas: (canvas) => { canvas.width = canvas.height = 0; },
  find: async () => { if (state.holdSearch) await new Promise<void>((resolve) => { state.releaseSearch = resolve; }); return 3; },
  cancelSearch: () => undefined, cancelRender: () => undefined, close: () => { state.closes += 1; },
});
Object.assign(window, { __VIEWER_UI_TEST__: state }); state.mount();
