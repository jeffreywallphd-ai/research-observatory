import { describe, expect, it } from "vitest";
import { decodeReferencePage } from "./documentReferences";
import { referenceReaderFixture } from "../../../../tests/desktop/fixtures/reference-reader";
const project = "00000000-0000-7000-8000-000000000001", revision = "00000000-0000-7000-8000-000000000003";
describe("bounded reference inspection", () => {
  it("keeps source revisions and raw Unicode text distinct from verification", () => {
    const value = decodeReferencePage(referenceReaderFixture(), project, revision);
    expect(value?.entries[0]?.rawPreview).toBe("Synthetic reference 📚");
    expect(value?.scholarlyVerification).toBe("unverified");
  });
  it("rejects source substitution, fabricated targets, count drift and extra authority", () => {
    for (const change of [
      (v: MutableFixture) => { v.source.projectId = revision; },
      (v: MutableFixture) => { v.entries[0]!.linkState = "exact-linked"; },
      (v: MutableFixture) => { v.entries[0]!.rawLength = 20; },
      (v: MutableFixture) => { v.entries[0]!["actorId"] = revision; },
      (v: MutableFixture) => { v.entries[0]!.anchor["structureSha256"] = "d".repeat(64); },
      (v: MutableFixture) => { v["nextAfterOrder"] = 0; },
    ]) {
      const value = referenceReaderFixture() as MutableFixture; change(value);
      expect(decodeReferencePage(value, project, revision)).toBeNull();
    }
  });
  it("rejects accessor payloads without evaluating untrusted getters", () => {
    const value = referenceReaderFixture() as Record<string, unknown>;
    let invoked = false;
    Object.defineProperty(value, "entries", { get: () => { invoked = true; return []; } });
    expect(decodeReferencePage(value, project, revision)).toBeNull();
    expect(invoked).toBe(false);
  });
  it("rejects nested coercion and inherited serialization without invoking code", () => {
    const value = referenceReaderFixture() as MutableFixture;
    let invoked = false;
    value.entries[0]!["linkState"] = { toString: () => { invoked = true; return "unresolved"; } };
    expect(decodeReferencePage(value, project, revision)).toBeNull();
    expect(invoked).toBe(false);
    const inherited = Object.assign(Object.create({ toJSON: () => { invoked = true; return {}; } }) as Record<string, unknown>, referenceReaderFixture());
    expect(decodeReferencePage(inherited, project, revision)).toBeNull();
    expect(invoked).toBe(false);
  });
});
interface MutableFixture extends Record<string, unknown> {
  source: { projectId: string }; entries: (Record<string, unknown> & { anchor: Record<string, unknown> })[];
}
