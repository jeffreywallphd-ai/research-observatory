import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import {
  DiagnosticsWorkspace,
  decodeSupportBundleExport,
  decodeSupportBundlePreview,
} from "./DiagnosticsWorkspace";

const traceId = "0123456789abcdef0123456789abcdef";
const preview = {
  previewId: "a".repeat(32),
  outputDirectory: "C:\\Users\\Researcher\\AppData\\Local\\Research Observatory\\support-exports",
  byteLength: 2048,
  sha256: "b".repeat(64),
  bundle: {
    schemaVersion: "1.0",
    documentType: "research-observatory-support-bundle",
    bundleId: "c".repeat(32),
    generatedAtUnixMs: 1_786_534_400_000,
    components: [
      { componentId: "desktop", version: "0.1.0", contractVersion: "1.0.0" },
      { componentId: "core-api", version: "0.1.0", contractVersion: "1.0.0" },
    ],
    runtime: { state: "ready", attempt: 1, retryAvailable: false, diagnosticReference: null },
    storage: [{ storageId: "application-data", status: "available" }],
    resources: { processRunning: true, workingSetBytes: 62_000_000 },
    recentDiagnostics: [{ sequence: 1, code: "RO-CORE-API-REQUEST-COMPLETE", stream: "api", traceId }],
    exclusions: [
      "project-documents", "imported-sources", "manuscript-content", "search-and-query-text",
      "credentials-and-tokens", "environment-variables", "raw-process-logs", "process-identifiers",
      "absolute-storage-paths",
    ],
  },
};

describe("functional diagnostics and support workspace", () => {
  it("renders an accessible bounded collection state without reference content", () => {
    const html = renderToStaticMarkup(<DiagnosticsWorkspace announce={vi.fn()} />);
    expect(html).toContain('data-diagnostics-workspace="true"');
    expect(html).toContain("Diagnostics &amp; support");
    expect(html).toContain("Collecting bounded local diagnostics");
    expect(html).not.toContain("prototype-index.html");
    expect(html).not.toContain("mock study");
  });

  it("accepts only the exact bounded preview with trace-linked diagnostics", () => {
    expect(decodeSupportBundlePreview(preview)).toEqual(preview);
    expect(decodeSupportBundlePreview({ ...preview, secret: "Bearer hunter2" })).toBeNull();
    expect(decodeSupportBundlePreview({ ...preview, byteLength: 65_537 })).toBeNull();
    expect(decodeSupportBundlePreview({
      ...preview,
      bundle: { ...preview.bundle, recentDiagnostics: [{ ...preview.bundle.recentDiagnostics[0], traceId: "../private" }] },
    })).toBeNull();
    expect(decodeSupportBundlePreview({
      ...preview,
      bundle: { ...preview.bundle, exclusions: preview.bundle.exclusions.slice(1) },
    })).toBeNull();
    expect(decodeSupportBundlePreview({
      ...preview,
      bundle: { ...preview.bundle, storage: [{ storageId: "application-data", status: "unavailable" }] },
    })?.bundle.storage[0].status).toBe("unavailable");
  });

  it("binds export identity, size, hash, and a bounded display path", () => {
    const exported = { bundleId: "c".repeat(32), path: "C:\\support\\bundle.json", byteLength: 2048, sha256: "b".repeat(64) };
    expect(decodeSupportBundleExport(exported)).toEqual(exported);
    expect(decodeSupportBundleExport({ ...exported, path: "C:\\private\nsecret" })).toBeNull();
    expect(decodeSupportBundleExport({ ...exported, sha256: "forged" })).toBeNull();
  });
});
