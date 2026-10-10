// Authored synthetic preview. No scholarly quality or actual authority proof.
import { sourceAnchorFixture } from "./anchor-contract";
export function citationReaderFixture(): unknown {
  const anchor = (sourceAnchorFixture() as { target: Record<string, unknown> }).target;
  return { schemaVersion: "1.0", projectId: anchor["projectId"], source: anchor["source"], documentRevisionId: anchor["revisionId"],
    collectionId: "00000000-0000-7000-8000-000000000051", collectionRevisionId: "00000000-0000-7000-8000-000000000052",
    referenceCollectionId: "00000000-0000-7000-8000-000000000041", referenceCollectionRevisionId: "00000000-0000-7000-8000-000000000042",
    contentSha256: anchor["contentSha256"], structureSha256: anchor["structureSha256"], total: 1, afterOrder: null, nextAfterOrder: null,
    scholarlyVerification: "unverified", entries: [{ order: 0, canonicalCitationId: null, nodeId: anchor["nodeId"], textOffset: 8, nodeTextStart: 0,
      markerPreview: "📚", markerLength: 1, markerTruncated: false, style: "numeric", knowledgeStatus: "inferred", resolution: "candidate",
      targets: [{ label: "1", resolution: "candidate", referenceCount: 1, references: [{ referenceId: "00000000-0000-7000-8000-000000000043",
        nodeId: anchor["nodeId"], order: 0, linkState: "unresolved", target: null }] }], targetCount: 1,
      anchor, anchorTruncated: false, paragraph: { nodeId: anchor["nodeId"], projectionId: anchor["projectionId"], normalizedRange: { start: 0, end: 16 },
        markerRange: { start: 8, end: 9 }, textPreview: "Préface 📚 chosen", textLength: 16, previewStart: 0, truncated: false, basis: "source-element" },
      sentence: null, contextReason: "available", confidence: { state: "unknown", value: null } }],
  };
}
