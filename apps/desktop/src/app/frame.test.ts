import { describe, expect, it } from "vitest";

import {
  REQUIRED_FRAME_REGIONS,
  frameContractErrors,
  nextNavigationIndex,
  routeFromNavigationHref,
} from "./frame";

describe("application frame", () => {
  it("requires every approved shell region", () => {
    const selectors = new Set<string>(REQUIRED_FRAME_REGIONS.map(([, selector]) => selector));
    const complete = { querySelector: (selector: string) => (selectors.has(selector) ? ({} as Element) : null) };
    expect(frameContractErrors(complete)).toEqual([]);

    selectors.delete("aside.sidebar nav.nav-scroll");
    expect(frameContractErrors(complete)).toEqual([
      "missing application frame navigation rail: aside.sidebar nav.nav-scroll",
    ]);
  });

  it("moves through the navigation rail without a pointer", () => {
    expect(nextNavigationIndex(0, 4, "ArrowDown")).toBe(1);
    expect(nextNavigationIndex(3, 4, "ArrowDown")).toBe(0);
    expect(nextNavigationIndex(0, 4, "ArrowUp")).toBe(3);
    expect(nextNavigationIndex(2, 4, "Home")).toBe(0);
    expect(nextNavigationIndex(1, 4, "End")).toBe(3);
    expect(nextNavigationIndex(0, 0, "Home")).toBe(-1);
  });

  it("accepts only local approved workspace links", () => {
    expect(routeFromNavigationHref("study-design.html?project=demo#protocol")).toBe("study-design.html");
    expect(routeFromNavigationHref(["https", "example.invalid/study-design.html"].join("://"))).toBeNull();
    expect(routeFromNavigationHref("../study-design.html")).toBeNull();
    expect(routeFromNavigationHref("../index.html")).toBeNull();
    expect(routeFromNavigationHref("%68ttps%3A%2F%2Fexample.invalid/study-design.html")).toBeNull();
    expect(routeFromNavigationHref("/%252e%252e/study-design.html")).toBeNull();
    expect(routeFromNavigationHref("/%5c/study-design.html")).toBeNull();
    expect(routeFromNavigationHref("/%2f%2fevil.invalid/study-design.html")).toBeNull();
    expect(routeFromNavigationHref("/%68ttps%3A%2F%2Fevil.invalid/study-design.html")).toBeNull();
    expect(routeFromNavigationHref("unknown.html")).toBeNull();
  });
});
