import { useEffect, useRef, useState, type ReactNode } from "react";
import type { ConnectorDiagnostics, ConnectorInspection, ConnectorRecentRuns, createCoreApiClient } from "@research-observatory/contracts/core-api";
import type { createConnectorDiagnosticsClient } from "@research-observatory/contracts/connector-diagnostics";
import { Button, Field, Notification, Panel, Typography } from "@research-observatory/ui-components";

export function diagnosticsMatchInspection(inspection: ConnectorInspection, diagnostics: ConnectorDiagnostics | null): boolean {
  if (!diagnostics || !( ["previewId", "invocationId", "jobId", "workflowRunId", "providerId", "operation", "state", "updatedAt", "diagnosticCode"] as const).every(key => inspection.job[key] === diagnostics.job[key])) return false;
  if (inspection.observation === null) return diagnostics.observation === null;
  const observed = diagnostics.observation;
  return observed !== null && (["observationId", "observedAt", "outcome", "continuation"] as const).every(key => inspection.observation![key] === observed[key]);
}

export function SourceRequestHistory({ root, client, diagnosticsClient, active, selection }: {
  readonly root: string;
  readonly client: ReturnType<typeof createCoreApiClient>;
  readonly diagnosticsClient: ReturnType<typeof createConnectorDiagnosticsClient>;
  readonly active: boolean;
  readonly selection: { readonly previewId: string } | null;
}): ReactNode {
  const [recent, setRecent] = useState<ConnectorRecentRuns | null>(null);
  const [selected, setSelected] = useState("");
  const [inspection, setInspection] = useState<ConnectorInspection | null>(null);
  const [diagnostics, setDiagnostics] = useState<ConnectorDiagnostics | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [missing, setMissing] = useState(false);
  const generation = useRef(0);
  const live = useRef(active);
  const inFlight = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);

  async function read(id: string | null, offset = 0, focus = false): Promise<void> {
    if (!live.current || inFlight.current) return;
    inFlight.current = true;
    const ticket = ++generation.current;
    setBusy(true); setFailure(null); setMissing(false);
    if (id !== null) { setSelected(id); setInspection(null); setDiagnostics(null); }
    try {
      if (id === null) {
        const page = await client.recentSourceRequests({ root });
        if (live.current && ticket === generation.current) setRecent(page);
      } else {
        const item = await client.inspectSourceRequest({ root, previewId: id, recordOffset: offset });
        if (!live.current || ticket !== generation.current) return;
        setInspection(item); setMissing(item === null);
        if (item) {
          try {
            const facts = await diagnosticsClient.inspect({ root, previewId: id });
            if (live.current && ticket === generation.current && diagnosticsMatchInspection(item, facts)) setDiagnostics(facts);
          } catch {
            // Scholarly inspection remains usable when operational facts are unavailable.
            if (live.current && ticket === generation.current) setDiagnostics(null);
          }
        }
      }
    } catch {
      if (live.current && ticket === generation.current) setFailure("The protected request record could not be verified. No source request was sent. Check that this project is open and try the read-only inspection again.");
    } finally {
      if (ticket === generation.current) {
        inFlight.current = false;
        if (live.current) { setBusy(false); if (focus) heading.current?.focus(); }
      }
    }
  }
  useEffect(() => {
    live.current = active; inFlight.current = false;
    setRecent(null); setSelected(""); setInspection(null); setDiagnostics(null);
    setMissing(false); setFailure(null); setBusy(false);
    if (active) void read(null);
    return () => { live.current = false; generation.current += 1; };
  }, [active, client, diagnosticsClient, root]);
  useEffect(() => {
    if (active && selection) {
      // A newer explicit inspection replaces a read-only list request only.
      generation.current += 1; inFlight.current = false;
      void read(selection.previewId, 0, true);
    }
  }, [active, selection]);

  const observed = inspection?.observation;
  const facts = diagnostics?.observation;
  const measured = facts?.measurements;
  const row = observed?.records[0];
  return <section className="ro-stack" aria-labelledby="source-history-title">
    <h2 id="source-history-title" ref={heading} tabIndex={-1}>Source request history</h2>
    <Panel title="Inspect retained requests">
      <Typography>Read-only inspection never resends a request. Recent activity shows up to 20 source jobs from the latest 100 project workflows, not complete provider coverage. An exact preview ID can locate an older or unconfirmed submission.</Typography>
      <div className="ro-action-row"><Button disabled={!active || busy} onClick={() => void read(null)}>Refresh source request history</Button></div>
      {recent?.items.length === 0 ? <p>No source jobs found in the recent workflow window. This does not establish that a request succeeded or returned no records.</p> : null}
      {recent?.items.length ? <ul>{recent.items.map((item) => <li key={item.previewId}><Button disabled={!active || busy} onClick={() => void read(item.previewId, 0, true)}>Inspect {item.providerId} · {item.operation} · {item.updatedAt}</Button><p className="ro-wrap-anywhere">{item.state} · Preview {item.previewId}</p></li>)}</ul> : null}
      <Field id="source-inspect-id" label="Exact source preview ID" description="Shown before sending and retained with every submitted source task." input={{ value: selected, disabled: busy, maxLength: 36, onChange: (event) => { setSelected(event.currentTarget.value); setInspection(null); setDiagnostics(null); setMissing(false); } }} />
      <Button disabled={!active || busy || !/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(selected)} onClick={() => void read(selected, 0, true)}>Inspect exact source request</Button>
      {busy ? <p role="status">Reading protected source history…</p> : null}
      {failure ? <Notification tone="warning" title="Inspection unavailable">{failure}</Notification> : null}
      {missing ? <Notification tone="warning" title="No scheduled job found for this preview">This is not a successful empty result and does not prove that an in-flight confirmation cannot finish. Do not automatically resend; refresh the exact inspection after the pending action settles or the application restarts.</Notification> : null}
      {inspection ? <div className="ro-stack" data-source-inspection>
        <dl className="ro-key-value ro-wrap-anywhere"><dt>Source</dt><dd>{inspection.job.providerId}</dd><dt>Job state</dt><dd>{inspection.job.state}</dd><dt>Preview ID</dt><dd>{inspection.job.previewId}</dd><dt>Request ID</dt><dd>{inspection.job.invocationId}</dd><dt>Updated</dt><dd>{inspection.job.updatedAt}</dd><dt>Scientific query</dt><dd><code>{inspection.queryJson}</code></dd><dt>Query identity</dt><dd>{inspection.scientificRequestSha256}</dd></dl>
        {inspection.job.diagnosticCode ? <p>Diagnostic: {inspection.job.diagnosticCode}</p> : null}
        {observed ? <>
          <dl className="ro-key-value"><dt>Observation</dt><dd>{observed.outcome}</dd><dt>Observed at</dt><dd>{observed.observedAt}</dd><dt>Retrieved at</dt><dd>{observed.retrievedAt ?? "Not retrieved"}</dd><dt>Records on this page</dt><dd>{observed.recordCount} — not a total for the source</dd><dt>Continuation</dt><dd>{observed.continuation}</dd></dl>
          <div className="ro-stack" data-source-diagnostics>
            <h3>Request measurements</h3>
            <dl className="ro-key-value ro-wrap-anywhere">
              <dt>HTTP attempts</dt><dd>{measured?.httpRequests ?? "Unavailable"}</dd>
              <dt>Retries</dt><dd>{measured?.httpRetries ?? "Unavailable"}</dd>
              <dt>Request latency, all attempts</dt><dd>{measured?.exchangeElapsedMs !== null && measured?.exchangeElapsedMs !== undefined ? `${measured.exchangeElapsedMs} ms` : "Unavailable"}</dd>
              <dt>Broker time before storage</dt><dd>{measured ? `${measured.brokerElapsedMs} ms` : "Unavailable"}</dd>
              <dt>Last HTTP status</dt><dd>{measured?.lastHttpStatus ?? "Unavailable"}</dd>
              <dt>Response snapshot size</dt><dd>{facts?.responseByteLength !== null && facts?.responseByteLength !== undefined ? `${facts.responseByteLength} bytes` : "Unavailable"}</dd>
              <dt>Response retention</dt><dd>{facts?.responseBodyState ?? "Unavailable"}</dd>
              <dt>Cache</dt><dd>{facts ? `${facts.cacheState}${facts.cacheAgeMs !== null ? ` · ${facts.cacheAgeMs} ms old` : ""}` : "Unavailable"}</dd>
              <dt>Rate state</dt><dd>{facts?.rate.circuit ?? "Unavailable"}</dd>
              <dt>Reported remaining requests</dt><dd>{facts?.rate.remaining ?? "Unavailable"}</dd>
              <dt>Retry after</dt><dd>{facts?.rate.retryAfterMs !== null && facts?.rate.retryAfterMs !== undefined ? `${facts.rate.retryAfterMs} ms` : "Unavailable"}</dd>
              <dt>Error classes</dt><dd>{facts ? facts.errors.map(error => error.code).join(", ") || "None recorded" : "Unavailable"}</dd>
              <dt>Schema warnings</dt><dd>{facts ? facts.warnings.join(", ") || "None recorded" : "Unavailable"}</dd>
              <dt>Cursor progress</dt><dd>{facts ? `Page ${facts.pageIndex + 1}${facts.nextPageIndex !== null ? `; next page ${facts.nextPageIndex + 1}` : `; ${facts.continuation}`}` : "Unavailable"}</dd>
            </dl>
            <Typography variant="compact">Attempts can fail before reaching the provider. Latency totals the transport attempts and their cleanup, rounded up to milliseconds; broker time also includes local preparation and waits, but excludes storage. Snapshot size describes the sanitized response, not bytes on the network. A cache-only observation has zero attempts and unavailable request latency. Missing historical or unmatched measurements remain unavailable.</Typography>
          </div>
          {row ? <div className="ro-stack ro-wrap-anywhere"><h3>Source record {inspection.recordOffset + 1} of {observed.recordCount}</h3><p>{row.rawIdentifier.scheme}: {row.rawIdentifier.value}</p><p>Reported access: {row.terms.access}; license: {row.terms.license.value ?? row.terms.license.state}; terms: {row.terms.terms.value ?? row.terms.terms.state}</p>
            {row.fields.map((field) => <div key={field.name}><h4>{field.name === "candidate.title" ? "Title" : field.name === "candidate.oa-locations" ? "Reported open-access locations, hosts and licenses" : "Discovery direction and seeds"}</h4><p>{field.value}</p></div>)}
            <p>Only title, open-access locations and discovery fields are projected here; absence is not an inferred value. These source observations do not grant download, model, sharing or export permission.</p>
          </div> : null}
          <div className="ro-action-row">{inspection.recordOffset > 0 ? <Button disabled={busy} onClick={() => void read(inspection.job.previewId, inspection.recordOffset - 1)}>Previous source record</Button> : null}{inspection.nextRecordOffset !== null ? <Button disabled={busy} onClick={() => void read(inspection.job.previewId, inspection.nextRecordOffset!)}>Next source record</Button> : null}</div>
        </> : <Notification tone="info" title="No accepted observation yet">The job record exists, but no source result is available for inspection. No successful or zero-record coverage is implied.</Notification>}
      </div> : null}
    </Panel>
  </section>;
}
