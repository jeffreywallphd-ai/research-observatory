import { describe, expect, it } from "vitest";
import { decodeAnchorResolution, decodeCitationLinks, decodeSourceAnchor } from "./sourceAnchors";
import { sourceAnchorFixture } from "../../../../tests/desktop/fixtures/anchor-contract";

const id = (n: number): string => `00000000-0000-7000-8000-${n.toString(16).padStart(12, "0")}`;
function fixture() {
  const anchor = decodeSourceAnchor(sourceAnchorFixture(), id(1), id(3))!;
  const metadata = { projectId: id(1), documentId: id(2), revisionId: id(3),
    acceptedAt: "2026-10-08T00:00:00.000Z", displayLabel: "Synthetic source", labelOrigin: "canonical-document-revision" };
  return { schemaVersion: "1.0", anchorId: anchor.anchorId, anchorRevisionId: anchor.anchorRevisionId,
    source: anchor.target.source, metadata, status: "fallback", selectorUsed: "structural-text", reason: null,
    target: anchor.target, propagation: null, scholarlyVerification: "unverified" };
}

describe("exact source resolution and reference uncertainty", () => {
  it("keeps retained context on the requested source and denies mixed identities", () => {
    const value = fixture();
    expect(decodeAnchorResolution(value, id(1), id(3), value.anchorId)?.status).toBe("fallback");
    expect(decodeAnchorResolution(value, id(1), id(4), value.anchorId)).toBeNull();
    expect(decodeAnchorResolution(value, id(1), id(3), id(98))).toBeNull();
    expect(decodeAnchorResolution({ ...value, metadata: { ...value.metadata, documentId: id(98) } }, id(1), id(3), value.anchorId)).toBeNull();
    expect(decodeAnchorResolution({ ...value, selectorUsed: "page-region" }, id(1), id(3), value.anchorId)).toBeNull();
    expect(decodeAnchorResolution({ ...value, scholarlyVerification: "verified" }, id(1), id(3), value.anchorId)).toBeNull();
  });

  it("distinguishes missing text from completed broken-anchor stale propagation", () => {
    const value = fixture();
    const missing = { ...value, target: null, status: "missing", selectorUsed: "not-resolved", reason: "readable-text-not-reported" };
    expect(decodeAnchorResolution(missing, id(1), id(3), value.anchorId)?.status).toBe("missing");
    const broken = { ...missing, status: "broken", reason: "protected-context-unavailable",
      propagation: { runId: id(90), state: "completed", totalItems: 2, processedItems: 2, staleCount: 2, unknownCount: 0 } };
    expect(decodeAnchorResolution(broken, id(1), id(3), value.anchorId)?.propagation?.staleCount).toBe(2);
    expect(decodeAnchorResolution({ ...broken, propagation: { ...broken.propagation, processedItems: 1 } }, id(1), id(3), value.anchorId)).toBeNull();
    expect(decodeAnchorResolution({ ...missing, propagation: broken.propagation }, id(1), id(3), value.anchorId)).toBeNull();
    expect(decodeAnchorResolution({ ...broken, target: value.target }, id(1), id(3), value.anchorId)).toBeNull();
  });

  it("retains reference ambiguity with bounded exact targets and cursor", () => {
    const anchor = fixture();
    const row = { referenceId: id(91), target: anchor.target, previewTruncated: false };
    const value = { schemaVersion: "1.0", citationId: id(92), source: anchor.source, metadata: anchor.metadata,
      marker: anchor.target, markerTruncated: false, resolution: "ambiguous", totalCandidates: 2, targets: [row],
      nextReferenceId: row.referenceId, scholarlyVerification: "unverified" };
    expect(decodeCitationLinks(value, id(1), id(3), id(92))?.resolution).toBe("ambiguous");
    for (const change of [{ resolution: "candidate" }, { nextReferenceId: id(99) }, { targets: [row, row] },
      { targets: [row, row, row] }, { scholarlyVerification: "verified" }, { url: "untrusted-reference" }]) {
      expect(decodeCitationLinks({ ...value, ...change }, id(1), id(3), id(92))).toBeNull();
    }
    expect(decodeCitationLinks({ ...value, totalCandidates: 0, targets: [], nextReferenceId: null, resolution: "unresolved" }, id(1), id(3), id(92))?.targets).toEqual([]);
    expect(decodeCitationLinks(value, id(1), id(4), id(92))).toBeNull();
  });
});
