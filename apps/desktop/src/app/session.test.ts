import { describe, expect, it } from "vitest";

import { transitionProjectSession } from "./session";

describe("project session state", () => {
  it("opens a validated project", () => {
    expect(transitionProjectSession("no-project", "opening")).toBe("opening");
    expect(transitionProjectSession("opening", "ready")).toBe("ready");
  });

  it("fails closed for an invalid transition", () => {
    expect(() => transitionProjectSession("no-project", "ready")).toThrow(
      "invalid project session transition",
    );
  });
});
