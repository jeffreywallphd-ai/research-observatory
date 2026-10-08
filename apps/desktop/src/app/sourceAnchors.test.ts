import { describe, expect, it } from "vitest";
import { codepointRangeToUtf16, decodeSourceAnchor, pageRegionPixels, type SourceAnchorTarget } from "./sourceAnchors";
import { sourceAnchorFixture } from "../../../../tests/desktop/fixtures/anchor-contract";

const id = (n: number): string => `00000000-0000-7000-8000-${n.toString(16).padStart(12, "0")}`;

describe("immutable source selectors in the renderer", () => {
  it("converts Core codepoints to UTF16 without normalization or passage movement", () => {
    expect(codepointRangeToUtf16("Préface 📚 chosen", { start: 8, end: 9 })).toEqual({ start: 8, end: 10 });
    expect(codepointRangeToUtf16("📚a📚", { start: 1, end: 3 })).toEqual({ start: 2, end: 5 });
    expect(() => codepointRangeToUtf16("text", { start: 0, end: 5 })).toThrow();
    expect(() => codepointRangeToUtf16("\ud800", { start: 0, end: 1 })).toThrow();
  });

  it("keeps the exact revision and a typed visible missing-coordinate fallback", () => {
    const receipt = decodeSourceAnchor(sourceAnchorFixture(), id(1), id(3));
    expect(receipt?.target.revisionId).toBe(id(3));
    expect(receipt?.target.coordinatesState).toBe("format-has-no-pages");
    expect(receipt?.target.quote?.exact).toBe("📚");
    expect(receipt?.target.confidence).toEqual({ state: "unknown", value: null });
    expect(decodeSourceAnchor(sourceAnchorFixture(), id(2), id(3))).toBeNull();
    expect(decodeSourceAnchor(sourceAnchorFixture(), id(1), id(4))).toBeNull();
  });

  it("rejects contradictory selectors rather than silently selecting another passage", () => {
    const wire = sourceAnchorFixture() as { target: Record<string, unknown> };
    wire.target["quote"] = { exact: "different", prefix: "", suffix: "" };
    expect(decodeSourceAnchor(wire, id(1), id(3))).toBeNull();
  });

  it("keeps normalized source geometry invariant under display scaling and rotation", () => {
    const region: NonNullable<SourceAnchorTarget["pageRegion"]> = {
      pageIndex: 0, pageNumber: 1, x0: 0.1, y0: 0.2, x1: 0.5, y1: 0.5, sourceWidth: 600, sourceHeight: 800,
      rotation: 90, frame: "unrotated-source-page", origin: "top-left", unit: "normalized", granularity: "block",
    };
    expect(pageRegionPixels(region, 800, 600)).toEqual({ x: 400, y: 60, width: 240, height: 240 });
    expect(pageRegionPixels(region, 1200, 900)).toEqual({ x: 600, y: 90, width: 360, height: 360 });
    expect(region).toMatchObject({ x0: 0.1, y0: 0.2, rotation: 90 });
    expect(() => pageRegionPixels(region, Number.NaN, 900)).toThrow();
  });
});
