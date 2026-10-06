import { describe, expect, it } from "vitest";
import { decodeCopies, decodeCopyReview, nativeDocumentAcquisitionPort } from "./documentAcquisition";
import type { AttachmentSelection } from "./documentAttachment";

const id = (suffix: number): string => `01900000-0000-7000-8000-${suffix.toString().padStart(12, "0")}`;
const selection: AttachmentSelection = { projectId: id(1), workId: id(2), workRevisionId: id(3), versionId: id(4), versionRevisionId: id(5), sourceAssertionRevisionId: id(6) };
const copy = { copyId: id(7), copySha256: "a".repeat(64), provider: "Synthetic provider", host: "oa.example.invalid", license: null, version: null };
const inventory = { schemaVersion: "1.0", selection, copies: [copy], retained: [{ candidateId: id(8), originalOperationId: id(9), sourceName: "synthetic.pdf" }] };
const preview = { schemaVersion: "1.0", selection, reviewId: id(10), copy, redirectHosts: [], storeInspect: "allowed", egress: "confirmed-preview-required" };

describe("exact native copy metadata", () => {
  it("preserves the approved UUID4 project bridge while keeping revision identities UUID7", () => {
    const bridged = { ...selection, projectId: "01890f47-eae3-4cc0-98c4-dc0c0c073981" };
    expect(decodeCopies({ ...inventory, selection: bridged }, bridged)?.copies).toEqual([copy]);
  });
  it("keeps distinct observations even when their protected bytes may be deduplicated", () => {
    const alternate = { ...copy, copyId: id(11), copySha256: "b".repeat(64), license: "CC-BY", version: "accepted" };
    const decoded = decodeCopies({ ...inventory, copies: [copy, alternate] }, selection);
    expect(decoded?.copies).toEqual([copy, alternate]);
    expect(decoded?.retained).toEqual(inventory.retained);
  });
  it("rejects URL, secret, path, unknown-field and substituted association metadata", () => {
    for (const field of ["url", "confirmation", "path", "cookies"]) {
      expect(decodeCopies({ ...inventory, copies: [{ ...copy, [field]: "untrusted" }] }, selection)).toBeNull();
      expect(decodeCopyReview({ ...preview, [field]: "untrusted" }, selection, copy)).toBeNull();
    }
    expect(decodeCopies({ ...inventory, selection: { ...selection, versionRevisionId: id(12) } }, selection)).toBeNull();
    expect(decodeCopyReview({ ...preview, copy: { ...copy, license: "changed" } }, selection, copy)).toBeNull();
    expect(decodeCopyReview({ ...preview, redirectHosts: ["other.example.invalid"] }, selection, copy)).toBeNull();
    expect(decodeCopies({ ...inventory, copies: [copy, copy] }, selection)).toBeNull();
  });
  it("does not execute a property getter while decoding untrusted metadata", () => {
    let called = false;
    const altered = { ...inventory };
    Object.defineProperty(altered, "copies", { enumerable: true, get() { called = true; throw new Error("getter"); } });
    expect(decodeCopies(altered, selection)).toBeNull();
    expect(called).toBe(false);
  });
  it("requires the native runtime and never uses browser fetch for download or notes", async () => {
    expect(await nativeDocumentAcquisitionPort.copies(selection)).toBeNull();
    expect(await nativeDocumentAcquisitionPort.review(selection, copy)).toBeNull();
    expect(await nativeDocumentAcquisitionPort.download(selection, { reviewId: id(10), copy, redirectHosts: [] }, id(13))).toMatchObject({ status: "unavailable" });
    expect(await nativeDocumentAcquisitionPort.annotate(selection, null, id(14), "unknown", "institutional")).toBe(false);
  });
});
