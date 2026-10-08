// Authored synthetic Unicode selector fixture; no study/parser-quality claim.
const id = (n: number): string => `00000000-0000-7000-8000-${n.toString(16).padStart(12, "0")}`;
export function sourceAnchorFixture(): unknown {
  return { schemaVersion: "1.0", anchorId: id(20), anchorRevisionId: id(21), createdAt: "2026-10-08T00:00:00.000Z",
    target: { schemaVersion: "1.0", projectId: id(1), documentId: id(2), revisionId: id(3),
      source: { projectId: id(1), attachmentId: id(4), documentId: id(2), documentRevisionId: id(5), candidateId: id(6),
        sourceAssertionRevisionId: id(7), workId: id(8), workRevisionId: id(9), versionId: id(10), versionRevisionId: id(11),
        objectSha256: "a".repeat(64), byteLength: 100, format: "plain-text", provenance: { kind: "local-import" } },
      contentSha256: "b".repeat(64), structureSha256: "c".repeat(64), nodeId: id(12), nodeKind: "paragraph",
      blockId: id(12), sentenceId: null, projectionId: id(13), normalizationVersion: "ro-text-nfc-1", unicodeVersion: "16.0.0",
      textPosition: { start: 8, end: 9 }, quote: { exact: "📚", prefix: "Préface ", suffix: " chosen" },
      context: { start: 0, text: "Préface 📚 chosen", highlight: { start: 8, end: 9 } },
      pageRegion: null, coordinatesState: "format-has-no-pages", confidence: { state: "unknown", value: null },
      scholarlyVerification: "unverified" } };
}
