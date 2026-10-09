import { describe, expect, it } from "vitest";
import { decodeViewerDeepLink, parseViewerDeepLink, readStoredViewerDeepLink, rememberViewerDeepLink,
  viewerDeepLinkUri } from "./viewerDeepLinks";

const id = (n: number): string => "00000000-0000-7000-8000-" + n.toString(16).padStart(12, "0");
const link = { schemaVersion: "1.0", projectId: id(1), selector: {
  attachmentId: id(4), documentRevisionId: id(5), normalizedRevisionId: id(3),
}, anchorIds: [id(20), id(22)] };

describe("portable exact-revision Reader links", () => {
  it("round-trips ordered opaque IDs with no machine, session or protected context", () => {
    const value = decodeViewerDeepLink(link)!;
    const uri = viewerDeepLinkUri(value);
    expect(parseViewerDeepLink(uri)).toEqual(value);
    const legacyProject = { ...link, projectId: "00000000-0000-4000-8000-000000000001" };
    expect(parseViewerDeepLink(viewerDeepLinkUri(legacyProject as typeof value))).toEqual(legacyProject);
    expect(uri).toContain("research-observatory://reader/v1/");
    expect(uri).not.toMatch(/root|session|token|quote|context/u);
    expect(value.anchorIds).toEqual([id(20), id(22)]);
    link.anchorIds.reverse();
    expect(value.anchorIds).toEqual([id(20), id(22)]);
    link.anchorIds.reverse();
  });
  it("rejects extra authority, duplicate anchors, wrong versions and unavailable accepted revision", () => {
    for (const value of [{ ...link, root: "untrusted" }, { ...link, quote: "untrusted" },
      { ...link, schemaVersion: "2.0" }, { ...link, anchorIds: [] },
      { ...link, anchorIds: [id(20), id(20)] }, { ...link, anchorIds: Array.from({ length: 101 }, (_, n) => id(n + 30)) },
      { ...link, selector: { ...link.selector, sessionId: id(99) } },
      { ...link, selector: { ...link.selector, normalizedRevisionId: null } },
      { ...link, selector: { ...link.selector, normalizedRevisionId: id(5) } }]) {
      expect(decodeViewerDeepLink(value)).toBeNull();
    }
    const getter = Object.defineProperty({ ...link }, "projectId", { get: () => { throw new Error("getter ran"); } });
    expect(decodeViewerDeepLink(getter)).toBeNull();
  });
  it("does not reinterpret external, path, encoded, unknown-version or appended URI input", () => {
    const uri = viewerDeepLinkUri(decodeViewerDeepLink(link)!);
    for (const value of ["https://example.invalid/" + uri, uri.replace("/v1/", "/v0/"), uri + "?token=untrusted",
      uri + "#quote", uri.replace(id(1), "../"), uri.replace(id(1), encodeURIComponent("/untrusted")), " " + uri]) {
      expect(parseViewerDeepLink(value)).toBeNull();
    }
  });
  it("retains only the link projection and revalidates storage for the exact explicitly opened project", () => {
    const values = new Map<string, string>();
    const storage = { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, value); } };
    const value = decodeViewerDeepLink(link)!;
    expect(rememberViewerDeepLink(storage, value)).toBe(true);
    expect(readStoredViewerDeepLink(storage, id(1))).toEqual(value);
    expect(readStoredViewerDeepLink(storage, id(99))).toBeNull();
    expect(Array.from(values.values())).toEqual([viewerDeepLinkUri(value)]);
    storage.setItem(Array.from(values.keys())[0]!, viewerDeepLinkUri({ ...value, projectId: id(99) }));
    expect(readStoredViewerDeepLink(storage, id(1))).toBeNull();
    expect(rememberViewerDeepLink({ ...storage, setItem: () => { throw new Error("storage denied"); } }, value)).toBe(false);
  });
});
