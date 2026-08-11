import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import {
  LOCAL_SERVICE_DIAGNOSTIC_REFERENCE,
  LocalServiceBoundary,
  packagedLocalServiceProbe,
  secretSafeServiceFailure,
} from "./LocalServiceBoundary";

describe("local service recovery boundary", () => {
  it("renders a truthful actionable state without dropping local shell content", () => {
    const markup = renderToStaticMarkup(<LocalServiceBoundary announce={vi.fn()} />);

    expect(markup).toContain('data-boundary-state="recovery-required"');
    expect(markup).toContain(LOCAL_SERVICE_DIAGNOSTIC_REFERENCE);
    expect(markup).toContain("Retry");
    expect(markup).toContain("Continue locally");
    expect(markup).toContain("Copy diagnostic reference");
    expect(markup).toContain("no researcher data is discarded");
  });

  it("maps hostile adapter failures to an opaque secret-safe diagnostic", () => {
    const failure = secretSafeServiceFailure(
      new Error("Bearer super-secret api_key=hunter2 C:\\Users\\researcher\\private-project"),
    );
    const serialized = JSON.stringify(failure);

    expect(failure.state).toBe("failed");
    expect(failure.diagnosticReference).toBe(LOCAL_SERVICE_DIAGNOSTIC_REFERENCE);
    expect(serialized).not.toContain("super-secret");
    expect(serialized).not.toContain("hunter2");
    expect(serialized).not.toContain("researcher");
  });

  it("returns the actual not-packaged state and honors cancellation", async () => {
    const active = new AbortController();
    await expect(packagedLocalServiceProbe(active.signal)).resolves.toEqual({
      status: "unavailable",
      diagnosticReference: LOCAL_SERVICE_DIAGNOSTIC_REFERENCE,
    });

    const cancelled = new AbortController();
    cancelled.abort();
    await expect(packagedLocalServiceProbe(cancelled.signal)).rejects.toMatchObject({ name: "AbortError" });
  });
});
