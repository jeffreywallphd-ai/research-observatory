// Authored synthetic inspection projection. No parser/scholarly-quality claim.
import { sourceAnchorFixture } from "./anchor-contract";
export function referenceReaderFixture(): unknown {
  const base = sourceAnchorFixture() as { target: Record<string, unknown> };
  const target: Record<string, unknown> = { ...base.target, nodeKind: "reference", blockId: null };
  return { schemaVersion: "1.0", projectId: target["projectId"], source: target["source"],
    documentRevisionId: target["revisionId"], collectionId: "00000000-0000-7000-8000-000000000041",
    collectionRevisionId: "00000000-0000-7000-8000-000000000042", contentSha256: target["contentSha256"], structureSha256: target["structureSha256"],
    total: 1, afterOrder: null, nextAfterOrder: null, scholarlyVerification: "unverified",
    entries: [{ referenceId: "00000000-0000-7000-8000-000000000043", nodeId: target["nodeId"], order: 0,
      rawPreview: "Synthetic reference 📚", rawLength: 21, rawTruncated: false,
      fields: [], identifiers: [], identifierCount: 0, linkState: "unresolved", target: null,
      candidates: [], candidateCount: 0, matchFlags: [], anchor: target, anchorTruncated: false }],
  };
}
