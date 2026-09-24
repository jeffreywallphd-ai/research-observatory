import { useEffect, useRef, useState, type ReactNode } from "react";
import type { ConnectorInspection, ConnectorRecentRuns, createCoreApiClient } from "@research-observatory/contracts/core-api";
import { Button, Field, Notification, Panel, Typography } from "@research-observatory/ui-components";

export function SourceRequestHistory({ root, client, active, selection }: {
  readonly root: string;
  readonly client: ReturnType<typeof createCoreApiClient>;
  readonly active: boolean;
  readonly selection: { readonly previewId: string } | null;
}): ReactNode {
  const [recent, setRecent] = useState<ConnectorRecentRuns | null>(null);
  const [selected, setSelected] = useState("");
  const [inspection, setInspection] = useState<ConnectorInspection | null>(null);
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
    if (id !== null) { setSelected(id); setInspection(null); }
    try {
      if (id === null) {
        const page = await client.recentSourceRequests({ root });
        if (live.current && ticket === generation.current) setRecent(page);
      } else {
        const item = await client.inspectSourceRequest({ root, previewId: id, recordOffset: offset });
        if (live.current && ticket === generation.current) { setInspection(item); setMissing(item === null); }
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
    if (active) void read(null);
    return () => { live.current = false; generation.current += 1; };
  }, [active, client, root]);
  useEffect(() => {
    if (active && selection) {
      // A newer explicit inspection replaces a read-only list request only.
      generation.current += 1; inFlight.current = false;
      void read(selection.previewId, 0, true);
    }
  }, [active, selection]);

  const observed = inspection?.observation;
  const row = observed?.records[0];
  return <section className="ro-stack" aria-labelledby="source-history-title">
    <h2 id="source-history-title" ref={heading} tabIndex={-1}>Source request history</h2>
    <Panel title="Inspect retained requests">
      <Typography>Read-only inspection never resends a request. Recent activity shows up to 20 source jobs from the latest 100 project workflows, not complete provider coverage. An exact preview ID can locate an older or unconfirmed submission.</Typography>
      <div className="ro-action-row"><Button disabled={!active || busy} onClick={() => void read(null)}>Refresh source request history</Button></div>
      {recent?.items.length === 0 ? <p>No source jobs found in the recent workflow window. This does not establish that a request succeeded or returned no records.</p> : null}
      {recent?.items.length ? <ul>{recent.items.map((item) => <li key={item.previewId}><Button disabled={!active || busy} onClick={() => void read(item.previewId, 0, true)}>Inspect {item.providerId} · {item.operation} · {item.updatedAt}</Button><p className="ro-wrap-anywhere">{item.state} · Preview {item.previewId}</p></li>)}</ul> : null}
      <Field id="source-inspect-id" label="Exact source preview ID" description="Shown before sending and retained with every submitted source task." input={{ value: selected, disabled: busy, maxLength: 36, onChange: (event) => { setSelected(event.currentTarget.value); setInspection(null); setMissing(false); } }} />
      <Button disabled={!active || busy || !/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(selected)} onClick={() => void read(selected, 0, true)}>Inspect exact source request</Button>
      {busy ? <p role="status">Reading protected source history…</p> : null}
      {failure ? <Notification tone="warning" title="Inspection unavailable">{failure}</Notification> : null}
      {missing ? <Notification tone="warning" title="No scheduled job found for this preview">This is not a successful empty result and does not prove that an in-flight confirmation cannot finish. Do not automatically resend; refresh the exact inspection after the pending action settles or the application restarts.</Notification> : null}
      {inspection ? <div className="ro-stack" data-source-inspection>
        <dl className="ro-key-value ro-wrap-anywhere"><dt>Source</dt><dd>{inspection.job.providerId}</dd><dt>Job state</dt><dd>{inspection.job.state}</dd><dt>Preview ID</dt><dd>{inspection.job.previewId}</dd><dt>Request ID</dt><dd>{inspection.job.invocationId}</dd><dt>Updated</dt><dd>{inspection.job.updatedAt}</dd><dt>Scientific query</dt><dd><code>{inspection.queryJson}</code></dd><dt>Query identity</dt><dd>{inspection.scientificRequestSha256}</dd></dl>
        {inspection.job.diagnosticCode ? <p>Diagnostic: {inspection.job.diagnosticCode}</p> : null}
        {observed ? <>
          <dl className="ro-key-value"><dt>Observation</dt><dd>{observed.outcome}</dd><dt>Observed at</dt><dd>{observed.observedAt}</dd><dt>Retrieved at</dt><dd>{observed.retrievedAt ?? "Not retrieved"}</dd><dt>Records on this page</dt><dd>{observed.recordCount} — not a total for the source</dd><dt>Continuation</dt><dd>{observed.continuation}</dd></dl>
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
