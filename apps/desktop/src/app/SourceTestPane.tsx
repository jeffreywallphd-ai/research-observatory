import { useEffect, useRef, useState, type ReactNode } from "react";
import { CoreApiClientError, sourceTestCommand, type ConnectorCapabilities, type ConnectorJobStatus, type ConnectorPreview, type ProjectProjection, type createCoreApiClient } from "@research-observatory/contracts/core-api";
import { Button, Field, Notification, Panel, StatusBadge, Typography } from "@research-observatory/ui-components";

/** UUIDv7 uses a local timestamp for identity, not evidence of provider time. */
export function sourceInvocationId(now = Date.now()): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  let time = BigInt(now);
  for (let i = 5; i >= 0; i--) { bytes[i] = Number(time & 255n); time >>= 8n; }
  bytes[6] = (bytes[6]! & 15) | 112; bytes[8] = (bytes[8]! & 63) | 128;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
export function sourceJobLabel(job: ConnectorJobStatus): string {
  if (job.state === "succeeded") return "Request succeeded — accepted observations retained";
  if (job.state === "failed") return "Request failed — no successful coverage implied";
  if (job.state === "cancelled") return "Request cancelled";
  return `Request ${job.state.replaceAll("-", " ")}`;
}
function failureMessage(error: unknown): string {
  return error instanceof CoreApiClientError
    ? `${error.problem.title} (${error.problem.code}). ${error.problem.detail} ${error.problem.remediation}`
    : "The local service response could not be verified. Check Task Center before making another request.";
}
const terminal = (job: ConnectorJobStatus): boolean => ["succeeded", "failed", "cancelled"].includes(job.state);

export function SourceTestPane({ project, provider, client, announce, onClose, onTasks, onInspect, active = true }: {
  readonly project: ProjectProjection;
  readonly provider: ConnectorCapabilities;
  readonly client: ReturnType<typeof createCoreApiClient>;
  readonly announce: (message: string) => void;
  readonly onClose: () => void;
  readonly onTasks?: (() => void) | undefined;
  readonly onInspect: (previewId: string) => void;
  readonly active?: boolean;
}): ReactNode {
  const [doi, setDoi] = useState("");
  const [rights, setRights] = useState(false);
  const [preview, setPreview] = useState<ConnectorPreview | null>(null);
  const [job, setJob] = useState<ConnectorJobStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [uncertain, setUncertain] = useState(false);
  const [submittedPreviewId, setSubmittedPreviewId] = useState<string | null>(null);
  const live = useRef(true);
  const inFlight = useRef(false);
  const generation = useRef(0);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    live.current = active;
    if (active) heading.current?.focus();
    return () => { live.current = false; generation.current += 1; };
  }, [active]);

  async function prepare(): Promise<void> {
    if (!rights || inFlight.current || !live.current) return;
    inFlight.current = true; const ticket = ++generation.current;
    setBusy(true); setFailure(null); setPreview(null);
    try {
      const next = await client.previewSourceTest(sourceTestCommand(project.root, project.projectId, provider, doi.trim(), sourceInvocationId()));
      if (!live.current || ticket !== generation.current) return;
      setPreview(next); announce("Review the exact source request before sending. No network request has been made.");
    } catch (error) { if (live.current && ticket === generation.current) setFailure(failureMessage(error)); }
    finally { inFlight.current = false; if (live.current) setBusy(false); }
  }
  async function confirm(): Promise<void> {
    if (!preview || inFlight.current || uncertain || !live.current) return;
    inFlight.current = true; const ticket = ++generation.current;
    setBusy(true); setFailure(null);
    setSubmittedPreviewId(preview.previewId);
    try {
      const next = await client.confirmSourceTest({ root: project.root, previewId: preview.previewId, confirmation: preview.confirmation });
      if (!live.current || ticket !== generation.current) {
        // Acknowledged late submission is cancelled only in its original open
        // project. Never present it as an unchanged/cancelled-before-send action.
        await client.cancelSourceTest({ root: project.root, jobId: next.jobId }).catch(() => undefined);
        return;
      }
      setJob(next); setPreview(null); announce(sourceJobLabel(next));
    } catch (error) {
      if (live.current && ticket === generation.current) {
        setUncertain(true); setFailure(`Submission outcome unconfirmed. ${failureMessage(error)}`);
      }
    } finally { inFlight.current = false; if (live.current) setBusy(false); }
  }
  async function refresh(cancel = false): Promise<void> {
    if (!job || inFlight.current || !live.current) return;
    inFlight.current = true; const ticket = ++generation.current;
    setBusy(true); setFailure(null);
    try {
      const next = await (cancel ? client.cancelSourceTest : client.sourceTestStatus)({ root: project.root, jobId: job.jobId });
      if (live.current && ticket === generation.current) { setJob(next); announce(sourceJobLabel(next)); }
    } catch (error) { if (live.current && ticket === generation.current) setFailure(failureMessage(error)); }
    finally { inFlight.current = false; if (live.current) setBusy(false); }
  }
  // Explicit refresh avoids background requests after a page is left and
  // preserves the durable Task Center route across application restarts.
  return <section className="ro-stack" aria-labelledby="source-test-title" onKeyDown={(event) => { if (event.key === "Escape" && !busy) { event.stopPropagation(); onClose(); } }}>
    <h2 id="source-test-title" ref={heading} tabIndex={-1}>Test {provider.providerId}</h2>
    <Panel title="One explicit DOI lookup"><Typography>Testing sends this DOI to the selected provider. It can retain the metadata or open-access location response in this encrypted project; it never downloads full text. Provider settings are injected privately by Core.</Typography>
      {!job && !uncertain ? <div className="ro-form">
        <Field id="source-test-doi" label="DOI to look up" description="Enter a DOI, such as 10.…/…. Do not enter private notes or a full-text URL." input={{ value: doi, disabled: busy || !!preview, maxLength: 2048, autoComplete: "off", onChange: (event) => { setDoi(event.currentTarget.value); setPreview(null); } }} />
        <label><input type="checkbox" checked={rights} disabled={busy || !!preview} onChange={(event) => { setRights(event.currentTarget.checked); setPreview(null); }} /> I have permission to store and inspect this response locally. Other rights remain unknown.</label>
        {!preview ? <Button disabled={busy || !rights || !doi.trim()} onClick={() => void prepare()}>Preview source request</Button> : <>
          <Notification tone="warning" title="Review before sending"><dl className="ro-key-value"><dt>Destination</dt><dd>{preview.destinationHost}</dd><dt>Operation</dt><dd>{preview.request.query.kind}</dd><dt>DOI</dt><dd>{doi.trim()}</dd><dt>Data retained</dt><dd>Metadata / location response in this project; no model, sharing or export permission granted</dd><dt>Terms</dt><dd>{preview.terms.terms.value ?? preview.terms.terms.state}</dd><dt>License</dt><dd>{preview.terms.license.value ?? preview.terms.license.state}</dd><dt>Preview expires</dt><dd>{preview.expiresAt}</dd></dl></Notification>
          <div className="ro-action-row"><Button disabled={busy} onClick={() => setPreview(null)}>Change request</Button><Button tone="primary" disabled={busy} onClick={() => void confirm()}>Send this DOI to {provider.providerId}</Button></div>
        </>}
      </div> : null}
      {job ? <><StatusBadge tone={job.state === "failed" ? "warning" : "info"}>{sourceJobLabel(job)}</StatusBadge><Typography variant="compact">This is one observed request, not a provider uptime score or complete source coverage. Source/query/time, rights and accepted observations retain their provenance.</Typography>{job.diagnosticCode ? <p>Diagnostic: {job.diagnosticCode}</p> : null}<div className="ro-action-row"><Button disabled={busy} onClick={() => void refresh()}>Refresh request status</Button>{!terminal(job) ? <Button disabled={busy} onClick={() => void refresh(true)}>Cancel source request</Button> : null}</div></> : null}
      {failure ? <Notification tone="warning" title={uncertain ? "Submission outcome unconfirmed" : "Source request unavailable"}>{failure}</Notification> : null}
      {preview || submittedPreviewId ? <p className="ro-wrap-anywhere">Source preview ID: {submittedPreviewId ?? preview?.previewId}</p> : null}
      {submittedPreviewId ? <Button disabled={busy} onClick={() => onInspect(submittedPreviewId)}>Inspect this source request</Button> : null}
      <div className="ro-action-row"><Button disabled={busy} onClick={onClose}>{job && !terminal(job) ? "Close panel — task continues" : "Close test panel"}</Button><Button disabled={!onTasks || busy} onClick={onTasks}>Open Task Center</Button></div>
    </Panel>
  </section>;
}
