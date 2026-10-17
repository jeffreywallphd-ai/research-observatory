import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SearchSnippetText, SearchWorkspace, emptySearchState } from "./SearchWorkspace";

describe("lawful lexical search workspace", () => {
  it("offers no execution without a current authorized project", () => {
    const html = renderToStaticMarkup(<SearchWorkspace project={null} scopeKey={null}
      state={null} onStateChange={() => undefined} announce={() => undefined} onOpenSource={async () => false} />);
    expect(html).toContain("Search Studio");
    expect(html).toContain("Open a protected project");
    expect(html).not.toContain("Run search</button>");
    expect(emptySearchState("scope").page).toBeNull();
    expect(emptySearchState("scope").query).toBe("");
  });

  it("renders codepoint highlights as inert source text", () => {
    const html = renderToStaticMarkup(<SearchSnippetText snippet={{field:"title", start:0, end:11,
      text:"😀 <script>x", highlights:[{start:2,end:10}], truncated:true}} />);
    expect(html).toContain("😀 <mark>&lt;script&gt;</mark>x");
    expect(html).toContain("Preview truncated");
    expect(html).not.toContain("<script>");
  });
});
