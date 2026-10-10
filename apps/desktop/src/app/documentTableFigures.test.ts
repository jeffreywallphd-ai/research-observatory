import { describe, expect, it } from "vitest";
import { decodeTableFigurePage } from "./documentTableFigures";
import { tableFigureReaderFixture } from "../../../../tests/desktop/fixtures/table-figure-reader";
const project = "00000000-0000-7000-8000-000000000001", revision = "00000000-0000-7000-8000-000000000003";
interface Mutable extends Record<string, unknown> { source: Record<string, unknown>; entries: Record<string, unknown>[] }
describe("table and figure source/quality boundary", () => {
  it("preserves sparse dimensions, low quality, exact source pins and Unicode codepoints", () => {
    const page = decodeTableFigurePage(tableFigureReaderFixture(), project, revision);
    expect(page?.entries[0]?.rows).toBe(50000);
    expect(page?.entries[0]?.cells).toHaveLength(1);
    expect(page?.entries[0]?.cells[0]?.triage).toBe("low-confidence");
    expect(page?.entries[0]?.captions[0]?.textLength).toBe(1);
    expect(page?.scholarlyVerification).toBe("unverified");
  });
  it("refuses source substitutions, quality promotion, cursor drift and added authority", () => {
    for (const change of [
      (v: Mutable) => { v.source["projectId"] = revision; },
      (v: Mutable) => { (v.entries[0]!["preview"] as Record<string, unknown>)["objectSha256"] = "f".repeat(64); },
      (v: Mutable) => { (v.entries[0]!["cells"] as Record<string, unknown>[])[0]!["triage"] = "reported-confidence"; },
      (v: Mutable) => { v.entries[0]!["excluded"] = true; },
      (v: Mutable) => { v.entries[0]!["nextAfterCell"] = 0; },
      (v: Mutable) => { v.entries[0]!["cellCount"] = 0; },
      (v: Mutable) => { v.entries[0]!["actorId"] = revision; },
      (v: Mutable) => { (v.entries[0]!["jump"] as Record<string, unknown>)["nodeId"] = revision; },
    ]) {
      const value = tableFigureReaderFixture() as Mutable; change(value);
      expect(decodeTableFigurePage(value, project, revision)).toBeNull();
    }
  });
  it("refuses getters, inherited serialization, oversized text and throwing proxies", () => {
    let invoked = false;
    const value = tableFigureReaderFixture() as Mutable;
    Object.defineProperty(value, "entries", { get: () => { invoked = true; return []; } });
    expect(decodeTableFigurePage(value, project, revision)).toBeNull(); expect(invoked).toBe(false);
    const inherited = Object.assign(Object.create({ toJSON: () => { invoked = true; return {}; } }) as Mutable, tableFigureReaderFixture());
    expect(decodeTableFigurePage(inherited, project, revision)).toBeNull(); expect(invoked).toBe(false);
    expect(decodeTableFigurePage(new Proxy({}, { getPrototypeOf() { throw new Error("untrusted"); } }), project, revision)).toBeNull();
    const large = tableFigureReaderFixture() as Mutable;
    (large.entries[0]!["captions"] as Record<string, unknown>[])[0]!["textPreview"] = "x".repeat(65537);
    expect(decodeTableFigurePage(large, project, revision)).toBeNull();
  });
});
