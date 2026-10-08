const MESSAGE_LIMIT = 16 * 1024 * 1024;

// Inspect only the fixed SDK's cloneable message graph. No source URL or HTML
// is evaluated. The guard runs before a decoded message is cloned to the UI.
export function viewerMessageFootprint(value: unknown): { bytes: number; buffers: ArrayBuffer[]; objects: object[] } {
  const seen = new Set<object>(), buffers: ArrayBuffer[] = [], objects: object[] = [], pending: unknown[] = [value];
  let bytes = 0, nodes = 0;
  while (pending.length) {
    const item = pending.pop();
    if (++nodes > 200000) throw new Error("viewer-resource-limit");
    if (typeof item === "string") bytes += item.length * 2;
    else if (item && typeof item === "object" && !seen.has(item)) {
      seen.add(item);
      objects.push(item);
      if (item instanceof ArrayBuffer) { bytes += item.byteLength; buffers.push(item); }
      else if (ArrayBuffer.isView(item)) pending.push(item.buffer);
      else {
        if (item instanceof Map) {
          if (item.size > 50000) throw new Error("viewer-resource-limit");
          bytes += item.size * 64;
          for (const [key, entry] of item) pending.push(key, entry);
          if (bytes > MESSAGE_LIMIT) throw new Error("viewer-resource-limit");
          continue;
        }
        if (item instanceof Set) {
          if (item.size > 100000) throw new Error("viewer-resource-limit");
          bytes += item.size * 48;
          for (const entry of item) pending.push(entry);
          if (bytes > MESSAGE_LIMIT) throw new Error("viewer-resource-limit");
          continue;
        }
        if (Array.isArray(item)) {
          if (item.length > 100000) throw new Error("viewer-resource-limit");
        } else if (!(item instanceof Error)) {
          // PDF.js uses its own ordinary exception/record classes. Structured
          // clone copies their own data fields, not prototypes or private fields.
          // Native objects with hidden cloneable storage (Blob, ImageBitmap,
          // Date, etc.) are not part of this viewer's message contract.
          if (Object.prototype.toString.call(item) !== "[object Object]") throw new Error("viewer-resource-limit");
        }
        const fields = Object.getOwnPropertyDescriptors(item);
        const keys = Reflect.ownKeys(fields);
        if (keys.length > 100000) throw new Error("viewer-resource-limit");
        bytes += keys.length * 48;
        for (const key of keys) {
          if (typeof key !== "string" || !("value" in fields[key]!)) throw new Error("viewer-resource-limit");
          pending.push(fields[key]!.value as unknown);
        }
      }
    }
    if (bytes > MESSAGE_LIMIT) throw new Error("viewer-resource-limit");
  }
  return { bytes, buffers, objects };
}

export function retainViewerMessage(event: MessageEvent<unknown>, worker: Worker, quota: { held: number }): void {
  const data = event.data;
  if (!data || typeof data !== "object" || !("viewerTransferId" in data) || typeof data.viewerTransferId !== "number") return;
  const identity = data.viewerTransferId;
  const { bytes, objects } = viewerMessageFootprint(data);
  if (bytes + quota.held > MESSAGE_LIMIT) throw new Error("viewer-resource-limit");
  quota.held += bytes;
  // PDF.js retains decoded objects as needed. Release their clone charge only
  // after the entire incoming message graph is no longer reachable.
  const collected = quotaCollectors.get(quota) ?? new FinalizationRegistry<MessageCharge>((held) => {
    held.remaining -= 1;
    if (held.remaining === 0) {
      quota.held -= held.bytes;
      worker.postMessage({ viewerReleaseId: held.id });
    }
  });
  quotaCollectors.set(quota, collected);
  const charge = { id: identity, bytes, remaining: objects.length };
  // Register every object, including retained child buffers. Collection of the
  // event envelope alone does not release decoded data still owned by PDF.js.
  for (const object of objects) collected.register(object, charge);
}
interface MessageCharge { readonly id: number; readonly bytes: number; remaining: number }
const quotaCollectors = new WeakMap<object, FinalizationRegistry<MessageCharge>>();
