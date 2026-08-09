import { describe, expect, it } from "vitest";

import { DESKTOP_ROUTES, resolveDesktopRoute } from "./routes";

describe("desktop routes", () => {
  it("contains the complete approved product route inventory", () => {
    expect(DESKTOP_ROUTES).toHaveLength(32);
    expect(new Set(DESKTOP_ROUTES).size).toBe(32);
  });

  it("resolves a known deep link", () => {
    expect(resolveDesktopRoute("/study-design.html?project=demo")).toBe("study-design.html");
    for (const route of DESKTOP_ROUTES) expect(resolveDesktopRoute(`/workspace/${route}`)).toBe(route);
  });

  it("recovers an invalid route to the safe project home", () => {
    expect(resolveDesktopRoute("/unknown-workspace.html")).toBe("index.html");
    expect(resolveDesktopRoute("/../study-design.html")).toBe("index.html");
    expect(resolveDesktopRoute("/%2e%2e/study-design.html")).toBe("index.html");
    expect(resolveDesktopRoute("/%252e%252e/study-design.html")).toBe("index.html");
    expect(resolveDesktopRoute("/%5c/study-design.html")).toBe("index.html");
    expect(resolveDesktopRoute("/%2f%2fevil.invalid/study-design.html")).toBe("index.html");
    expect(resolveDesktopRoute("/%68ttps%3A%2F%2Fevil.invalid/study-design.html")).toBe("index.html");
    expect(resolveDesktopRoute("https:evil.invalid/study-design.html")).toBe("index.html");
    expect(resolveDesktopRoute("mailto:user@example.invalid/study-design.html")).toBe("index.html");
    expect(resolveDesktopRoute(["https", "example.invalid/study-design.html"].join("://"))).toBe("index.html");
    expect(resolveDesktopRoute("\\study-design.html")).toBe("index.html");
    expect(resolveDesktopRoute("/%E0%A4%A")).toBe("index.html");
  });
});
