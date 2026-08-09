import { describe, expect, it } from "vitest";

import { DESKTOP_ROUTES, resolveDesktopRoute } from "./routes";

describe("desktop routes", () => {
  it("contains the complete approved product route inventory", () => {
    expect(DESKTOP_ROUTES).toHaveLength(32);
    expect(new Set(DESKTOP_ROUTES).size).toBe(32);
  });

  it("resolves a known deep link", () => {
    expect(resolveDesktopRoute("/study-design.html?project=demo")).toBe("study-design.html");
  });

  it("recovers an invalid route to the safe project home", () => {
    expect(resolveDesktopRoute("/unknown-workspace.html")).toBe("index.html");
  });
});
