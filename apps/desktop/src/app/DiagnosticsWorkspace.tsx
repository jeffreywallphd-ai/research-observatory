import { useCallback, useEffect, useState, type ReactNode } from "react";

import { invoke } from "@tauri-apps/api/core";
import { Button, Panel, StatusBadge, Typography } from "@research-observatory/ui-components";

const DIAGNOSTIC_STREAMS = new Set(["supervisor", "process", "stdout", "stderr", "api"]);
const EXPECTED_EXCLUSIONS = Object.freeze([
  "project-documents",
  "imported-sources",
  "manuscript-content",
  "search-and-query-text",
  "credentials-and-tokens",
  "environment-variables",
  "raw-process-logs",
  "process-identifiers",
  "absolute-storage-paths",
] as const);

interface ComponentVersion {
  readonly componentId: "desktop" | "core-api";
  readonly version: string;
  readonly contractVersion: string;
}

interface RuntimeSnapshot {
  readonly state: "starting" | "ready" | "crashed" | "stopped" | "incompatible" | "recovery-required";
  readonly attempt: number;
  readonly retryAvailable: boolean;
  readonly diagnosticReference: string | null;
}

interface RuntimeDiagnostic {
  readonly sequence: number;
  readonly code: string;
  readonly stream: string;
  readonly traceId: string | null;
}

interface SupportBundleDocument {
  readonly schemaVersion: "1.0";
  readonly documentType: "research-observatory-support-bundle";
  readonly bundleId: string;
  readonly generatedAtUnixMs: number;
  readonly components: readonly ComponentVersion[];
  readonly runtime: RuntimeSnapshot;
  readonly storage: readonly [{ readonly storageId: "application-data"; readonly status: "available" | "unavailable" }];
  readonly resources: { readonly processRunning: boolean; readonly workingSetBytes: number | null };
  readonly recentDiagnostics: readonly RuntimeDiagnostic[];
  readonly exclusions: typeof EXPECTED_EXCLUSIONS;
}

export interface SupportBundlePreview {
  readonly previewId: string;
  readonly outputDirectory: string;
  readonly byteLength: number;
  readonly sha256: string;
  readonly documentJson: string;
  readonly bundle: SupportBundleDocument;
}

export interface SupportBundleExport {
  readonly bundleId: string;
  readonly path: string;
  readonly byteLength: number;
  readonly sha256: string;
}

type PreviewProbe = () => Promise<unknown>;
type ExportProbe = (previewId: string) => Promise<unknown>;

function record(value: unknown): Readonly<Record<string, unknown>> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Readonly<Record<string, unknown>>
    : null;
}

function exactKeys(value: Readonly<Record<string, unknown>>, keys: readonly string[]): boolean {
  try {
    const actual = Object.keys(value).sort();
    const expected = [...keys].sort();
    return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
  } catch {
    return false;
  }
}

function canonicalHex(value: unknown, length: number): value is string {
  return typeof value === "string" && value.length === length && /^[0-9a-f]+$/.test(value);
}

function safeVersion(value: unknown): value is string {
  return typeof value === "string" && /^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$/.test(value);
}

function safePath(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= 512 && !/[\u0000-\u001f\u007f]/.test(value);
}

function safeInteger(value: unknown, maximum = Number.MAX_SAFE_INTEGER): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 && value <= maximum;
}

function decodeRuntime(value: unknown): RuntimeSnapshot | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, ["state", "attempt", "retryAvailable", "diagnosticReference"])) return null;
  if (!new Set(["starting", "ready", "crashed", "stopped", "incompatible", "recovery-required"]).has(String(candidate.state))) return null;
  if (!safeInteger(candidate.attempt, 3) || typeof candidate.retryAvailable !== "boolean") return null;
  if (candidate.diagnosticReference !== null
    && (typeof candidate.diagnosticReference !== "string" || !/^RO-CORE-[A-Z0-9-]+$/.test(candidate.diagnosticReference))) return null;
  return candidate as unknown as RuntimeSnapshot;
}

function decodeDiagnostic(value: unknown): RuntimeDiagnostic | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, ["sequence", "code", "stream", "traceId"])) return null;
  if (!safeInteger(candidate.sequence) || typeof candidate.code !== "string" || !/^RO-CORE-[A-Z0-9-]+$/.test(candidate.code)) return null;
  if (typeof candidate.stream !== "string" || !DIAGNOSTIC_STREAMS.has(candidate.stream)) return null;
  if (candidate.traceId !== null && !canonicalHex(candidate.traceId, 32)) return null;
  return candidate as unknown as RuntimeDiagnostic;
}

function decodeComponent(value: unknown): ComponentVersion | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, ["componentId", "version", "contractVersion"])) return null;
  if (candidate.componentId !== "desktop" && candidate.componentId !== "core-api") return null;
  if (!safeVersion(candidate.version) || !safeVersion(candidate.contractVersion)) return null;
  return candidate as unknown as ComponentVersion;
}

async function sha256(value: string): Promise<string> {
  const encoded = new TextEncoder().encode(value);
  const bytes = new Uint8Array(encoded.byteLength);
  bytes.set(encoded);
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes.buffer);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function decodeSupportBundlePreview(value: unknown): Promise<SupportBundlePreview | null> {
  try {
    const candidate = record(value);
    if (!candidate || !exactKeys(candidate, ["previewId", "outputDirectory", "byteLength", "sha256", "documentJson", "bundle"])) return null;
    if (!canonicalHex(candidate.previewId, 32) || !safePath(candidate.outputDirectory)
      || !safeInteger(candidate.byteLength, 65_536) || candidate.byteLength === 0 || !canonicalHex(candidate.sha256, 64)) return null;
    const bundle = record(candidate.bundle);
    if (!bundle || !exactKeys(bundle, [
      "schemaVersion", "documentType", "bundleId", "generatedAtUnixMs", "components", "runtime",
      "storage", "resources", "recentDiagnostics", "exclusions",
    ])) return null;
    if (bundle.schemaVersion !== "1.0" || bundle.documentType !== "research-observatory-support-bundle"
      || !canonicalHex(bundle.bundleId, 32) || !safeInteger(bundle.generatedAtUnixMs)) return null;
    if (!Array.isArray(bundle.components) || bundle.components.length !== 2) return null;
    const components = bundle.components.map(decodeComponent);
    if (components.some((item) => item === null)
      || components.map((item) => item?.componentId).join(",") !== "desktop,core-api") return null;
    const runtime = decodeRuntime(bundle.runtime);
    if (!runtime || !Array.isArray(bundle.storage) || bundle.storage.length !== 1) return null;
    const storage = record(bundle.storage[0]);
    if (!storage || !exactKeys(storage, ["storageId", "status"])
      || storage.storageId !== "application-data"
      || (storage.status !== "available" && storage.status !== "unavailable")) return null;
    const resources = record(bundle.resources);
    if (!resources || !exactKeys(resources, ["processRunning", "workingSetBytes"])
      || typeof resources.processRunning !== "boolean"
      || (resources.workingSetBytes !== null && !safeInteger(resources.workingSetBytes))) return null;
    if (!Array.isArray(bundle.recentDiagnostics) || bundle.recentDiagnostics.length > 32) return null;
    const diagnostics = bundle.recentDiagnostics.map(decodeDiagnostic);
    if (diagnostics.some((item) => item === null)
      || diagnostics.some((item, index) => index > 0 && (item?.sequence ?? 0) <= (diagnostics[index - 1]?.sequence ?? 0))) return null;
    if (!Array.isArray(bundle.exclusions)
      || bundle.exclusions.length !== EXPECTED_EXCLUSIONS.length
      || bundle.exclusions.some((item, index) => item !== EXPECTED_EXCLUSIONS[index])) return null;
    if (typeof candidate.documentJson !== "string") return null;
    const exactDocument = `${JSON.stringify(bundle, null, 2)}\n`;
    const exactBytes = new TextEncoder().encode(exactDocument);
    if (candidate.documentJson !== exactDocument
      || candidate.byteLength !== exactBytes.byteLength
      || candidate.sha256 !== await sha256(exactDocument)) return null;
    return {
      previewId: candidate.previewId,
      outputDirectory: candidate.outputDirectory,
      byteLength: candidate.byteLength,
      sha256: candidate.sha256,
      documentJson: candidate.documentJson,
      bundle: {
        schemaVersion: "1.0",
        documentType: "research-observatory-support-bundle",
        bundleId: bundle.bundleId as string,
        generatedAtUnixMs: bundle.generatedAtUnixMs as number,
        components: components as ComponentVersion[],
        runtime,
        storage: [{ storageId: "application-data", status: storage.status as "available" | "unavailable" }],
        resources: resources as unknown as SupportBundleDocument["resources"],
        recentDiagnostics: diagnostics as RuntimeDiagnostic[],
        exclusions: EXPECTED_EXCLUSIONS,
      },
    };
  } catch {
    return null;
  }
}

export function decodeSupportBundleExport(value: unknown): SupportBundleExport | null {
  const candidate = record(value);
  if (!candidate || !exactKeys(candidate, ["bundleId", "path", "byteLength", "sha256"])) return null;
  if (!canonicalHex(candidate.bundleId, 32) || !safePath(candidate.path)
    || !safeInteger(candidate.byteLength, 65_536) || candidate.byteLength === 0 || !canonicalHex(candidate.sha256, 64)) return null;
  return candidate as unknown as SupportBundleExport;
}

function hasTauriRuntime(): boolean {
  return typeof globalThis.window !== "undefined" && "__TAURI_INTERNALS__" in globalThis.window;
}

export async function packagedSupportPreview(): Promise<unknown> {
  if (!hasTauriRuntime()) throw new Error("RO-SUPPORT-HOST-UNAVAILABLE");
  return await invoke<unknown>("support_bundle_preview");
}

export async function packagedSupportExport(previewId: string): Promise<unknown> {
  if (!canonicalHex(previewId, 32) || !hasTauriRuntime()) throw new Error("RO-SUPPORT-PREVIEW-INVALID");
  return await invoke<unknown>("support_bundle_export", { previewId });
}

export interface DiagnosticsWorkspaceProps {
  readonly announce: (message: string) => void;
  readonly previewProbe?: PreviewProbe;
  readonly exportProbe?: ExportProbe;
}

export function DiagnosticsWorkspace({
  announce,
  previewProbe = packagedSupportPreview,
  exportProbe = packagedSupportExport,
}: DiagnosticsWorkspaceProps): ReactNode {
  const [preview, setPreview] = useState<SupportBundlePreview | null>(null);
  const [exported, setExported] = useState<SupportBundleExport | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "exporting" | "exported" | "unavailable">("loading");

  const refresh = useCallback(async () => {
    setState("loading");
    setExported(null);
    try {
      const decoded = await decodeSupportBundlePreview(await previewProbe());
      if (!decoded) throw new Error("RO-SUPPORT-PREVIEW-INVALID");
      setPreview(decoded);
      setState("ready");
      announce("Support bundle preview ready. Review every included and excluded category before export.");
    } catch {
      setPreview(null);
      setState("unavailable");
      announce("Diagnostics collection is unavailable. No support data was exported.");
    }
  }, [announce, previewProbe]);

  useEffect(() => { void refresh(); }, [refresh]);

  const exportBundle = useCallback(async () => {
    if (!preview) return;
    setState("exporting");
    try {
      const decoded = decodeSupportBundleExport(await exportProbe(preview.previewId));
      if (!decoded || decoded.bundleId !== preview.bundle.bundleId
        || decoded.byteLength !== preview.byteLength || decoded.sha256 !== preview.sha256) {
        throw new Error("RO-SUPPORT-EXPORT-INVALID");
      }
      setExported(decoded);
      setState("exported");
      announce("The exact reviewed support bundle was exported locally.");
    } catch {
      setExported(null);
      setState("ready");
      announce("Support bundle export failed. Refresh the preview before retrying; no project content was added.");
    }
  }, [announce, exportProbe, preview]);

  return (
    <section className="diagnostics-workspace" aria-labelledby="diagnostics-title" data-diagnostics-workspace>
      <div className="page-header">
        <Typography id="diagnostics-title" as="h1" variant="page-title">Diagnostics &amp; support</Typography>
        <Typography className="page-subtitle">
          Inspect local component health and review the exact redacted JSON bundle before exporting it.
        </Typography>
      </div>

      {state === "loading" ? <p role="status">Collecting bounded local diagnostics…</p> : null}
      {state === "unavailable" ? (
        <Panel title="Diagnostics unavailable" tone="warning">
          <p>The supervised desktop host is required. No support data was exported.</p>
          <Button onClick={() => { void refresh(); }}>Retry collection</Button>
        </Panel>
      ) : null}

      {preview ? (
        <>
          <div className="diagnostics-grid">
            <Panel title="Component versions" tone="neutral">
              <dl className="diagnostic-values">
                {preview.bundle.components.map((component) => (
                  <div key={component.componentId}>
                    <dt>{component.componentId === "desktop" ? "Desktop" : "Core API"}</dt>
                    <dd>{component.version} · contract {component.contractVersion}</dd>
                  </div>
                ))}
              </dl>
            </Panel>
            <Panel title="Runtime health" tone={preview.bundle.runtime.state === "ready" ? "success" : "warning"}>
              <StatusBadge tone={preview.bundle.runtime.state === "ready" ? "success" : "warning"}>
                {preview.bundle.runtime.state}
              </StatusBadge>
              <p>Attempt {preview.bundle.runtime.attempt} · working set {preview.bundle.resources.workingSetBytes === null
                ? "unavailable" : `${Math.ceil(preview.bundle.resources.workingSetBytes / 1_048_576)} MiB`}.</p>
              <p>Diagnostic reference: <code>{preview.bundle.runtime.diagnosticReference ?? "none"}</code></p>
            </Panel>
            <Panel title="Local storage" tone={preview.bundle.storage[0].status === "available" ? "success" : "warning"}>
              <StatusBadge tone={preview.bundle.storage[0].status === "available" ? "success" : "warning"}>
                {preview.bundle.storage[0].status === "available" ? "Available" : "Unavailable"}
              </StatusBadge>
              <p className="diagnostic-path">{preview.outputDirectory}</p>
              <p>{preview.bundle.storage[0].status === "available"
                ? "The displayed local path is not written into the exported bundle."
                : "Diagnostics remain inspectable, but export is unavailable until local storage is repaired."}</p>
            </Panel>
          </div>

          <section className="support-preview" aria-labelledby="support-preview-title">
            <div>
              <Typography id="support-preview-title" as="h2" variant="section-title">Exact support bundle preview</Typography>
              <p>{preview.byteLength.toLocaleString()} bytes · SHA-256 <code>{preview.sha256}</code></p>
            </div>
            <div className="support-columns">
              <div>
                <Typography as="h3" variant="card-title">Included</Typography>
                <ul>
                  <li>Desktop and Core versions</li>
                  <li>Runtime health and bounded resource use</li>
                  <li>Storage availability without absolute paths</li>
                  <li>Up to 32 code-only diagnostics and service trace IDs</li>
                </ul>
              </div>
              <div>
                <Typography as="h3" variant="card-title">Always excluded</Typography>
                <ul>{preview.bundle.exclusions.map((item) => <li key={item}>{item.replaceAll("-", " ")}</li>)}</ul>
              </div>
            </div>
            <details>
              <summary>Inspect exact redacted JSON document</summary>
              <pre className="support-json-preview">{preview.documentJson}</pre>
            </details>
            <Button tone="primary" disabled={state === "exporting" || state === "exported"} onClick={() => { void exportBundle(); }}>
              {state === "exporting" ? "Exporting…" : state === "exported" ? "Bundle exported" : "Export reviewed bundle"}
            </Button>
            <Button disabled={state === "exporting"} onClick={() => { void refresh(); }}>Refresh preview</Button>
            {exported ? <p role="status" className="diagnostic-path">Exported locally: {exported.path}</p> : null}
          </section>

          <section className="recent-diagnostics" aria-labelledby="recent-diagnostics-title">
            <Typography id="recent-diagnostics-title" as="h2" variant="section-title">Recent failures and trace links</Typography>
            {preview.bundle.recentDiagnostics.length ? (
              <div className="diagnostic-table-scroll"><table>
                <thead><tr><th scope="col">Sequence</th><th scope="col">Code</th><th scope="col">Source</th><th scope="col">Trace ID</th></tr></thead>
                <tbody>{preview.bundle.recentDiagnostics.map((item) => (
                  <tr key={item.sequence}><td>{item.sequence}</td><td><code>{item.code}</code></td><td>{item.stream}</td><td><code>{item.traceId ?? "not applicable"}</code></td></tr>
                ))}</tbody>
              </table></div>
            ) : <p>No recent diagnostic events are retained.</p>}
          </section>
        </>
      ) : null}
    </section>
  );
}
