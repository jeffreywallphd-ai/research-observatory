import { describe, expect, it } from "vitest";
import { decodeCitationPage } from "./documentCitations";
import { citationReaderFixture } from "../../../../tests/desktop/fixtures/citation-reader";
const project = "00000000-0000-7000-8000-000000000001", revision = "00000000-0000-7000-8000-000000000003";
interface Mutable extends Record<string, unknown> { source: Record<string, unknown>; entries: Record<string, unknown>[] }
describe("citation source and uncertainty boundary", () => {
  it("keeps exact codepoint offset and inferred targets distinct from verification", () => {
    const page = decodeCitationPage(citationReaderFixture(), project, revision);
    expect(page?.entries[0]?.textOffset).toBe(8);
    expect(page?.entries[0]?.markerPreview).toBe("📚");
    expect(page?.entries[0]?.knowledgeStatus).toBe("inferred");
    expect(page?.scholarlyVerification).toBe("unverified");
  });
  it("rejects source substitution, invented confidence, offset drift and extra authority", () => {
    for (const change of [
      (v: Mutable) => { v.source["projectId"] = revision; },
      (v: Mutable) => { v.entries[0]!["textOffset"] = 0; },
      (v: Mutable) => { v.entries[0]!["confidence"] = { state: "unknown", value: 0.9 }; },
      (v: Mutable) => { v.entries[0]!["actorId"] = revision; },
      (v: Mutable) => { v.entries[0]!["targetCount"] = 3; },
      (v: Mutable) => { v.entries[0]!["markerLength"] = 2; },
      (v: Mutable) => { v["nextAfterOrder"] = 0; },
    ]) {
      const value = citationReaderFixture() as Mutable; change(value);
      expect(decodeCitationPage(value, project, revision)).toBeNull();
    }
  });
  it("refuses accessor and inherited serialization without invoking code", () => {
    const value = citationReaderFixture() as Mutable; let invoked = false;
    Object.defineProperty(value, "entries", { get: () => { invoked = true; return []; } });
    expect(decodeCitationPage(value, project, revision)).toBeNull(); expect(invoked).toBe(false);
    const inherited = Object.assign(Object.create({ toJSON: () => { invoked = true; return {}; } }) as Mutable, citationReaderFixture());
    expect(decodeCitationPage(inherited, project, revision)).toBeNull(); expect(invoked).toBe(false);
  });
});
