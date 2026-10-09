import { PdfDocumentViewer } from "../../../apps/desktop/src/app/pdfDocumentViewer";
import { ViewerBufferBudget, ViewerByteSession } from "../../../apps/desktop/src/app/documentViewer";

// The browser/decoder is real. This authored test byte carrier is deliberately
// synthetic; Core encryption and Native ownership are proved separately.
const id = (number: number): string => `00000000-0000-7000-8000-${number.toString().padStart(12, "0")}`;
interface ProbeWindow extends Window {
  fixtureLength: number;
  readFixture: (start: number, end: number) => Promise<number[]>;
  decoderResult: object | undefined;
}
const probe = window as ProbeWindow;
const source = { projectId: id(1), attachmentId: id(2), documentId: id(3), documentRevisionId: id(4), candidateId: id(5),
  sourceAssertionRevisionId: id(6), workId: id(7), workRevisionId: id(8), versionId: id(9), versionRevisionId: id(10),
  objectSha256: "a".repeat(64), byteLength: probe.fixtureLength, format: "pdf" as const, provenance: { kind: "local-import" as const } };
const selector = { attachmentId: id(2), documentRevisionId: id(4), normalizedRevisionId: null };
const budget = new ViewerBufferBudget();
const bytes = new ViewerByteSession(id(1), selector, { source, normalizedRevisionId: null }, {
  source: async () => ({ source, normalizedRevisionId: null }),
  range: async (_project, _selector, _request, start, end, signal) => {
    const result = await probe.readFixture(start, end);
    return signal.aborted ? null : new Uint8Array(result).buffer;
  },
}, budget);
let failure: string | null = null;
const viewer = new PdfDocumentViewer(bytes, budget, (code) => { failure = code; });
const canvas = document.querySelector("canvas")!;
void (async () => {
  try {
    const pages = await viewer.open();
    await viewer.render(canvas, 1, 1);
    if (failure) throw new Error(failure);
    const textMatch = await viewer.find("Synthetic inert page", 0);
    probe.decoderResult = { outcome: "rendered", pages, width: canvas.width, height: canvas.height, textMatch };
  } catch (error) {
    probe.decoderResult = { outcome: "denied", code: error instanceof Error ? error.message : "unavailable" };
  } finally {
    viewer.close();
    await bytes.drain();
    probe.decoderResult = { ...probe.decoderResult, heldAfterClose: budget.used, canvasAfterClose: [canvas.width, canvas.height] };
  }
})();
