import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AnchorPassage, SourceAnchorReader } from "./SourceAnchorReader";
import { decodeSourceAnchor } from "./sourceAnchors";
import { sourceAnchorFixture } from "../../../../tests/desktop/fixtures/anchor-contract";

const anchor = decodeSourceAnchor(sourceAnchorFixture(), "00000000-0000-7000-8000-000000000001", "00000000-0000-7000-8000-000000000003")!;
describe("exact source passage presentation", () => {
  it("highlights the exact codepoint passage, labels text fallback and preserves revision at enlarged display", () => {
    for (const scale of [100, 150, 200]) {
      const html = renderToStaticMarkup(<AnchorPassage anchor={anchor} scale={scale} />);
      expect(html).toContain('<mark aria-label="Selected source passage">📚</mark>');
      expect(html).toContain("Structural/text fallback");
      expect(html).toContain(anchor.target.revisionId);
      expect(html).toContain("Confidence unknown");
      expect(html).toContain("Unverified extraction");
    }
  });
  it("renders protected text inertly rather than executing imported markup", () => {
    const text = '<script>alert("synthetic")</script>';
    const malicious = { ...anchor, target: { ...anchor.target, context: { start: 0, text, highlight: { start: 0, end: text.length } },
      textPosition: { start: 0, end: text.length }, quote: { exact: text, prefix: "", suffix: "" } } };
    const html = renderToStaticMarkup(<AnchorPassage anchor={malicious} scale={100} />);
    expect(html).toContain("&lt;script&gt;"); expect(html).not.toContain("<script>");
  });
  it("withholds all reader text while the project is locked", () => {
    const html = renderToStaticMarkup(<SourceAnchorReader source={anchor.target.source} revisionId={anchor.target.revisionId}
      active={false} announce={() => undefined} onReturn={() => undefined} />);
    expect(html).toContain("Unlock the project"); expect(html).not.toContain(anchor.target.source.attachmentId);
    expect(html).not.toContain("Préface");
  });
});
