import { installViewerWorkerQuota } from "./viewerWorkerQuota";
import { viewerMessageFootprint } from "./viewerWorkerMessages";

const scope = globalThis as unknown as { postMessage: (data: unknown, transfer?: Transferable[]) => void; close: () => void };
const quota = installViewerWorkerQuota(globalThis as unknown as Record<string, unknown>, 144 * 1024 * 1024);
const post = scope.postMessage.bind(scope), outstanding = new Map<number, number>();
let identity = 0, held = 0;
let ready = false;
const queued: MessageEvent<unknown>[] = [];
globalThis.addEventListener("message", (event: MessageEvent<unknown>) => {
  const data = event.data;
  if (data && typeof data === "object" && "viewerReleaseId" in data) {
    event.stopImmediatePropagation();
    if (typeof data.viewerReleaseId === "number") {
      held -= outstanding.get(data.viewerReleaseId) ?? 0; outstanding.delete(data.viewerReleaseId);
    }
    return;
  }
  try { for (const buffer of viewerMessageFootprint(data).buffers) quota.accept(buffer); }
  catch { event.stopImmediatePropagation(); post({ viewerFailure: "viewer-resource-limit" }); scope.close(); return; }
  if (!ready) {
    event.stopImmediatePropagation();
    if (queued.length >= 8) { post({ viewerFailure: "viewer-resource-limit" }); scope.close(); return; }
    queued.push(event);
  }
});
scope.postMessage = (data, transfer) => {
  const { bytes } = viewerMessageFootprint(data);
  if (held + bytes > 16 * 1024 * 1024 || !data || typeof data !== "object") throw new Error("viewer-resource-limit");
  const id = ++identity; held += bytes; outstanding.set(id, bytes);
  post({ ...data, viewerTransferId: id }, transfer);
};
// Static, locally bundled module; no document-controlled module specifier.
void import("pdfjs-dist/build/pdf.worker.mjs").then(() => {
  ready = true;
  for (const event of queued.splice(0)) globalThis.dispatchEvent(new MessageEvent("message", { data: event.data, ports: [...event.ports] }));
}).catch(() => {
  post({ viewerFailure: "viewer-resource-limit" });
  scope.close();
});
