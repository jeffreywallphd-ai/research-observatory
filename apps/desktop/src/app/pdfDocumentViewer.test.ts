import { afterEach, describe, expect, it, vi } from "vitest";
import { sourceAnchorFixture } from "../../../../tests/desktop/fixtures/anchor-contract";
import { decodeSourceAnchor } from "./sourceAnchors";
import { ViewerBufferBudget, ViewerByteSession } from "./documentViewer";
import { PdfDocumentViewer } from "./pdfDocumentViewer";

const sdk = vi.hoisted(() => ({ document: null as unknown, destroyed: 0, terminated: 0 }));
vi.mock("pdfjs-dist", () => ({
  AnnotationMode: { DISABLE: 0 }, PDFDataRangeTransport: class {},
  PDFWorker: { create: () => ({ destroy: () => { sdk.destroyed += 1; } }) },
  getDocument: () => ({ promise: Promise.resolve(sdk.document), destroy: () => Promise.resolve() }),
}));
afterEach(() => vi.unstubAllGlobals());
function setup(getPage: (number: number) => Promise<unknown>): { viewer: PdfDocumentViewer; budget: ViewerBufferBudget } {
  vi.stubGlobal("Worker", class { addEventListener(): void {} terminate(): void { sdk.terminated += 1; } });
  sdk.document = { numPages: 3, getPage, cleanup: () => Promise.resolve() };
  const fixture = sourceAnchorFixture();
  const source = decodeSourceAnchor(fixture, "00000000-0000-7000-8000-000000000001", "00000000-0000-7000-8000-000000000003")!.target.source;
  const selector = { attachmentId: source.attachmentId, documentRevisionId: source.documentRevisionId, normalizedRevisionId: null };
  const budget = new ViewerBufferBudget(), bytes = new ViewerByteSession(source.projectId, selector, { source, normalizedRevisionId: null }, {
    source: async () => null, range: async () => null,
  }, budget);
  return { viewer: new PdfDocumentViewer(bytes, budget, () => undefined), budget };
}
const canvas = (): HTMLCanvasElement => ({ width: 0, height: 0, getContext: () => ({}) }) as unknown as HTMLCanvasElement;
function page(reject = false): { render: ReturnType<typeof vi.fn>; cleanup: ReturnType<typeof vi.fn>; getViewport: () => { width: number; height: number } } {
  return { getViewport: () => ({ width: 96, height: 128 }), cleanup: vi.fn(),
    render: vi.fn(() => ({ promise: reject ? Promise.reject(new Error("synthetic-render-failure")) : Promise.resolve(), cancel: vi.fn() })) };
}
describe("PDF thumbnail ownership during navigation", () => {
  it("settles cancellation while an uncached SDK page callback can no longer reply", async () => {
    const current = page();
    const { viewer, budget } = setup(async (number) => number === 2 ? new Promise(() => undefined) : current);
    await viewer.open();
    const searching = viewer.find("synthetic", 1);
    await new Promise((resolve) => setTimeout(resolve, 0));
    viewer.cancelSearch();
    expect(await Promise.race([searching, new Promise((_, reject) => setTimeout(() => reject(new Error("cancel-did-not-settle")), 50))])).toBeNull();
    await viewer.render(canvas(), 1, 1);
    expect(current.render).toHaveBeenCalledOnce();
    viewer.close(); expect(budget.used).toBe(0);
  });
  it("terminates a cancelled search generation and reopens the exact source for rendering", async () => {
    const current = page();
    const cancelled = vi.fn();
    const text = new ReadableStream({ cancel: cancelled });
    Object.assign(current, { streamTextContent: () => text });
    const { viewer, budget } = setup(async () => current);
    await viewer.open();
    const before = sdk.terminated, searching = viewer.find("synthetic", 0);
    await new Promise((resolve) => setTimeout(resolve, 0));
    viewer.cancelSearch();
    expect(sdk.terminated).toBe(before + 1);
    await viewer.render(canvas(), 1, 1);
    expect(await searching).toBeNull();
    expect(cancelled).toHaveBeenCalledOnce();
    expect(current.render).toHaveBeenCalledOnce();
    viewer.close(); expect(budget.used).toBe(0);
  });
  it("does not start a late thumbnail after the next navigation cancelled its generation", async () => {
    let finish: (value: unknown) => void = () => undefined;
    const late = page(), main = page(), pending = new Promise((resolve) => { finish = resolve; });
    const { viewer, budget } = setup(async (number) => number === 2 ? pending : main);
    await viewer.open();
    const image = canvas(), thumbnail = viewer.thumbnail(image, 2);
    await new Promise((resolve) => setTimeout(resolve, 0));
    await viewer.render(canvas(), 1, 1); finish(late); await thumbnail;
    expect(late.render).not.toHaveBeenCalled();
    // The cancelled caller settles before a deliberately late SDK callback.
    // Still require that callback to clean its page when it actually arrives.
    await vi.waitFor(() => expect(late.cleanup).toHaveBeenCalledOnce(), { timeout: 50, interval: 1 });
    expect(image.width).toBe(0); viewer.close(); expect(budget.used).toBe(0);
  });
  it("releases a rejected thumbnail's page and native canvas in its failure path", async () => {
    const failed = page(true), { viewer, budget } = setup(async () => failed);
    await viewer.open(); const image = canvas();
    await expect(viewer.thumbnail(image, 1)).rejects.toThrow("synthetic-render-failure");
    expect(failed.cleanup).toHaveBeenCalledOnce(); expect(image.width).toBe(0); expect(image.height).toBe(0);
    viewer.close(); expect(budget.used).toBe(0);
  });
});
