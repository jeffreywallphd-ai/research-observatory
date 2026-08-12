import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import {
  LOCAL_SERVICE_DIAGNOSTIC_REFERENCE,
  LocalServiceBoundary,
  decodeLocalServiceProbeResult,
  localServiceViewFromProbeResult,
  packagedLocalServiceProbe,
  secretSafeServiceFailure,
} from "./LocalServiceBoundary";

const ready = {
  state: "ready",
  attempt: 1,
  retryAvailable: false,
  diagnosticReference: null,
} as const;

describe("local service supervision boundary", () => {
  it("renders a truthful actionable host-unavailable state without dropping local shell content", () => {
    const markup = renderToStaticMarkup(<LocalServiceBoundary announce={vi.fn()} />);

    expect(markup).toContain('data-boundary-state="recovery-required"');
    expect(markup).toContain(LOCAL_SERVICE_DIAGNOSTIC_REFERENCE);
    expect(markup).toContain("Retry");
    expect(markup).toContain("Continue locally");
    expect(markup).toContain("Copy diagnostic reference");
    expect(markup).toContain("no researcher data is discarded");
    expect(markup).not.toContain("does not yet package");
  });

  it("renders the exact native ready and recovery states", () => {
    expect(localServiceViewFromProbeResult(ready)).toMatchObject({ state: "ready", retryAvailable: false });
    expect(localServiceViewFromProbeResult({
      state: "crashed",
      attempt: 1,
      retryAvailable: true,
      diagnosticReference: "RO-CORE-CRASHED",
    })).toMatchObject({ state: "failed", retryAvailable: true });
    expect(localServiceViewFromProbeResult({
      state: "recovery-required",
      attempt: 3,
      retryAvailable: false,
      diagnosticReference: "RO-CORE-RESTART-LIMIT",
    })).toMatchObject({ state: "recovery-required", retryAvailable: false });
    expect(localServiceViewFromProbeResult({
      state: "incompatible",
      attempt: 1,
      retryAvailable: true,
      diagnosticReference: "RO-CORE-INCOMPATIBLE",
    })).toMatchObject({
      state: "recovery-required",
      title: "Local analytical service is incompatible",
      message: "The desktop rejected the service handshake. Repair or reinstall the matching application package.",
      retryAvailable: true,
    });
  });

  it("maps hostile adapter failures to an opaque secret-safe diagnostic", () => {
    const failure = secretSafeServiceFailure(
      new Error("Bearer super-secret api_key=hunter2 C:\\Users\\researcher\\private-project"),
    );
    const serialized = JSON.stringify(failure);

    expect(failure.state).toBe("failed");
    expect(failure.diagnosticReference).toBe("RO-CORE-STATUS-FAILED");
    expect(serialized).not.toContain("super-secret");
    expect(serialized).not.toContain("hunter2");
    expect(serialized).not.toContain("researcher");
  });

  it.each([
    ["credential-shaped reference", { ...ready, diagnosticReference: "RO-TOKEN-HUNTER2-ABC123" }],
    ["URL and path content", {
      ...ready,
      diagnosticReference: `https:${String.fromCharCode(47, 47)}evil.invalid/C:/private?token=hunter2`,
    }],
    ["missing reference field", { state: "ready", attempt: 1, retryAvailable: false }],
    ["unsupported state", { ...ready, state: "future" }],
    ["noninteger attempt", { ...ready, attempt: 1.5 }],
    ["extra field", { ...ready, secret: "hunter2" }],
    ["array", ["ready", 1]],
    ["null", null],
    ["primitive", "Bearer hunter2"],
  ])("fails closed for an untrusted %s runtime snapshot", (_name, result) => {
    expect(decodeLocalServiceProbeResult(result)).toBeNull();
    const view = localServiceViewFromProbeResult(result);
    const serialized = JSON.stringify(view);

    expect(view.state).toBe("failed");
    expect(serialized).not.toContain("HUNTER2");
    expect(serialized).not.toContain("hunter2");
    expect(serialized).not.toContain("evil.invalid");
    expect(serialized).not.toContain("private");
  });

  it("accepts only the exact allowlisted snapshot and contains hostile property access", () => {
    expect(decodeLocalServiceProbeResult(ready)).toEqual(ready);
    const hostile = new Proxy({}, { ownKeys: () => { throw new Error("Bearer hunter2 C:\\private"); } });
    expect(() => localServiceViewFromProbeResult(hostile)).not.toThrow();
    expect(localServiceViewFromProbeResult(hostile)).toMatchObject({
      state: "failed",
      diagnosticReference: "RO-CORE-STATUS-FAILED",
    });
  });

  it("returns the bounded non-Tauri fallback and honors cancellation", async () => {
    const active = new AbortController();
    await expect(packagedLocalServiceProbe(active.signal)).resolves.toEqual({
      state: "recovery-required",
      attempt: 0,
      retryAvailable: true,
      diagnosticReference: LOCAL_SERVICE_DIAGNOSTIC_REFERENCE,
    });

    const cancelled = new AbortController();
    cancelled.abort();
    await expect(packagedLocalServiceProbe(cancelled.signal)).rejects.toMatchObject({ name: "AbortError" });
  });
});
