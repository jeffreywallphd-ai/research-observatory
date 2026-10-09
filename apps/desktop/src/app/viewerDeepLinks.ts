/** Portable selection only. It never opens a project or grants source access. */
export interface ViewerDeepLink {
  readonly schemaVersion: "1.0";
  readonly projectId: string;
  readonly selector: Readonly<{ attachmentId: string; documentRevisionId: string; normalizedRevisionId: string }>;
  readonly anchorIds: readonly string[];
}

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u;
const projectUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[47][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/u;
const prefix = "research-observatory://reader/v1/";
const keyPrefix = "research-observatory.reader-link.v1.";
export const VIEWER_LINK_EVENT = "research-observatory:reader-link";

function record(value: unknown, keys: readonly string[]): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const fields = Object.getOwnPropertyDescriptors(value);
  if (Reflect.ownKeys(value).length !== keys.length || keys.some(key => !fields[key] || !("value" in fields[key]!))) return null;
  return Object.fromEntries(keys.map(key => [key, fields[key]!.value]));
}
const identity = (value: unknown): value is string => typeof value === "string" && uuid.test(value);

export function decodeViewerDeepLink(value: unknown): ViewerDeepLink | null {
  try {
    const link = record(value, ["schemaVersion", "projectId", "selector", "anchorIds"]);
    const selector = record(link?.selector, ["attachmentId", "documentRevisionId", "normalizedRevisionId"]);
    if (!link || !selector || link.schemaVersion !== "1.0" || typeof link.projectId !== "string" || !projectUuid.test(link.projectId)
      || !identity(selector.attachmentId) || !identity(selector.documentRevisionId)
      || !identity(selector.normalizedRevisionId) || selector.normalizedRevisionId === selector.documentRevisionId
      || !Array.isArray(link.anchorIds) || link.anchorIds.length < 1 || link.anchorIds.length > 100) return null;
    const fields = Object.getOwnPropertyDescriptors(link.anchorIds);
    if (Reflect.ownKeys(link.anchorIds).length !== link.anchorIds.length + 1) return null;
    const anchors: string[] = [];
    for (let n = 0; n < link.anchorIds.length; n++) {
      const field = fields[String(n)];
      if (!field || !("value" in field) || !identity(field.value) || anchors.includes(field.value)) return null;
      anchors.push(field.value);
    }
    return Object.freeze({ schemaVersion: "1.0", projectId: link.projectId,
      selector: Object.freeze({ attachmentId: selector.attachmentId, documentRevisionId: selector.documentRevisionId,
        normalizedRevisionId: selector.normalizedRevisionId }), anchorIds: Object.freeze(anchors) });
  } catch { return null; }
}

export function viewerDeepLinkUri(value: ViewerDeepLink): string {
  const link = decodeViewerDeepLink(value);
  if (!link) throw new Error("viewer-link-selection-invalid");
  const s = link.selector;
  return prefix + [link.projectId, s.attachmentId, s.documentRevisionId, s.normalizedRevisionId, link.anchorIds.join(",")].join("/");
}

export function parseViewerDeepLink(value: unknown): ViewerDeepLink | null {
  if (typeof value !== "string" || value.length > 8192 || !value.startsWith(prefix)) return null;
  const fields = value.slice(prefix.length).split("/");
  if (fields.length !== 5) return null;
  return decodeViewerDeepLink({ schemaVersion: "1.0", projectId: fields[0], selector: {
    attachmentId: fields[1], documentRevisionId: fields[2], normalizedRevisionId: fields[3],
  }, anchorIds: fields[4]!.split(",") });
}

type LinkStorage = Pick<Storage, "getItem" | "setItem">;
export function rememberViewerDeepLink(storage: LinkStorage, value: ViewerDeepLink): boolean {
  try { storage.setItem(keyPrefix + value.projectId, viewerDeepLinkUri(value)); return true; } catch { return false; }
}
export function readStoredViewerDeepLink(storage: LinkStorage, projectId: string): ViewerDeepLink | null {
  if (!projectUuid.test(projectId)) return null;
  try {
    const link = parseViewerDeepLink(storage.getItem(keyPrefix + projectId));
    return link?.projectId === projectId ? link : null;
  } catch { return null; }
}
