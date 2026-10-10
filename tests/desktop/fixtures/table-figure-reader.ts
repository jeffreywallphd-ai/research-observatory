// Authored preview fixture, not parser or scholarly-quality qualification.
import { sourceAnchorFixture } from "./anchor-contract";
export function tableFigureReaderFixture(): unknown {
  const anchor = (sourceAnchorFixture() as { target: Record<string, unknown> }).target;
  const jump = { nodeId: anchor["nodeId"], nodeKind: "table", textOffset: 0, nodeTextStart: 0,
    normalizedRange: { start: 0, end: 1 }, pageNumber: 1 };
  const source = anchor["source"] as Record<string, unknown>;
  const cellId = "00000000-0000-7000-8000-000000000061";
  return { schemaVersion: "1.0", projectId: anchor["projectId"], source, documentRevisionId: anchor["revisionId"],
    collectionId: "00000000-0000-7000-8000-000000000071", collectionRevisionId: "00000000-0000-7000-8000-000000000072",
    contentSha256: anchor["contentSha256"], structureSha256: anchor["structureSha256"], total: 1,
    afterOrder: null, nextAfterOrder: null, scholarlyVerification: "unverified", entries: [{
      nodeId: anchor["nodeId"], kind: "table", order: 0, jump, captionState: "reported", captionCount: 1,
      captions: [{ nodeId: cellId, textPreview: "📚", textLength: 1, truncated: false,
        jump: { ...jump, nodeId: cellId, nodeKind: "caption", textOffset: 8, normalizedRange: { start: 8, end: 9 } } }],
      labelCount: 0, labels: [], rows: 50000, columns: 50000, gridState: "ambiguous", cellCount: 1,
      afterCell: null, nextAfterCell: null, cells: [{ nodeId: cellId, cellOrder: 0, textPreview: "A", textLength: 1,
        truncated: false, jump: { ...jump, nodeId: cellId, nodeKind: "table-cell" }, row: 1, column: 2,
        rowSpan: 2, columnSpan: 3, headerState: "not-reported", confidence: { state: "reported", value: 0.5 }, triage: "low-confidence" }],
      confidence: { state: "unknown", value: null }, preview: { kind: "source-page-region", sourceRevisionId: source["documentRevisionId"],
        objectSha256: source["objectSha256"], nodeId: anchor["nodeId"], basis: "object", scholarlyVerification: "unverified",
        locator: { kind: "page-region", pageIndex: 0, x0: 10, y0: 20, x1: 100, y1: 200,
          unit: "points", origin: "top-left", frame: "unrotated-source-page" } },
      retainedPreviewState: "not-reported", warnings: ["table-layout-unverified"], excluded: false, exclusion: null,
    }] };
}
