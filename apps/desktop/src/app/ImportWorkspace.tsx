import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createCoreApiClient, type CoreApiTransport, type ImportPreviewItem, type ImportPreviewPage, type ProjectProjection } from "@research-observatory/contracts/core-api";
import { Button, Notification, Panel, StatusBadge, Typography } from "@research-observatory/ui-components";
import { packagedProjectTransport } from "./ProjectsWorkspace";
import { chooseImportSource, type ImportIntakeOptions } from "./importIntake";
import { ImportReviewPane, importFailure, importStatusLabel } from "./ImportReviewPane";

export interface ImportWorkspaceProps {
  readonly project: ProjectProjection | null;
  readonly announce: (message: string) => void;
  readonly transport?: CoreApiTransport;
  readonly initialPreviews?: ImportPreviewPage;
}

export function ImportWorkspace(props: ImportWorkspaceProps): ReactNode {
  const project = props.project;
  if (!project?.open) return <Notification tone="info" title="No project open">Open a local project before importing or reviewing references.</Notification>;
  if (project.accessMode !== "read-write" || project.compatibilityState !== "compatible") return <Notification tone="warning" title="Import review unavailable in read-only mode">Open a compatible working copy read-write. No import or mapping changes have been made.</Notification>;
  // Changing or locking the project unmounts every private draft and cancels
  // its owned intake; a fresh mount never restores protected renderer state.
  return <ImportProject key={`${project.projectId}\u0000${project.root}`} {...props} project={project} />;
}

function ImportProject({ project, announce, transport = packagedProjectTransport, initialPreviews }: ImportWorkspaceProps & { readonly project: ProjectProjection }): ReactNode {
  const client = useMemo(() => createCoreApiClient(transport), [transport]);
  const [page, setPage] = useState<ImportPreviewPage | null>(initialPreviews ?? null);
  const [after, setAfter] = useState<string | null>(null);
  const [selected, setSelected] = useState<ImportPreviewItem | null>(null);
  const [loading, setLoading] = useState(initialPreviews === undefined);
  const [failure, setFailure] = useState<string | null>(null);
  const [choosing, setChoosing] = useState(false);
  const [options, setOptions] = useState<ImportIntakeOptions>({ formatName: "ris", encoding: "utf-8", localUseConfirmed: false });
  const live = useRef(true);
  const libraryGeneration = useRef(0);
  const intake = useRef<AbortController | null>(null);
  const chooseButton = useRef<HTMLButtonElement>(null);

  async function load(cursor: string | null): Promise<void> {
    const generation = ++libraryGeneration.current;
    setLoading(true); setFailure(null);
    try {
      const next = await client.importPreviews({ root: project.root, after: cursor, limit: 25 });
      if (!live.current || generation !== libraryGeneration.current) return;
      setPage(next); setAfter(cursor);
    } catch (error) {
      if (live.current && generation === libraryGeneration.current) { setPage(null); setFailure(importFailure(error)); }
    } finally { if (live.current && generation === libraryGeneration.current) setLoading(false); }
  }
  useEffect(() => {
    live.current = true;
    if (initialPreviews === undefined) void load(null);
    return () => { live.current = false; libraryGeneration.current += 1; intake.current?.abort(); };
  }, [client, project.root]);

  async function choose(): Promise<void> {
    if (choosing) return;
    const owner = new AbortController(); intake.current = owner;
    setChoosing(true); setFailure(null);
    try {
      const result = await chooseImportSource(project, options, owner.signal);
      if (!live.current || owner.signal.aborted) {
        // Publication may have completed just before native cancellation. Revoke
        // that exact preview if its original project remains open; never replay
        // against a different project or display the late source name.
        if (result.status === "prepared") await client.cancelImportPreview({ root: project.root, previewId: result.preview.previewId }).catch(() => undefined);
        return;
      }
      if (result.status === "prepared") {
        setSelected(result.preview); announce("Source retained locally. Parsing is queued; no canonical import has been committed.");
        await load(null);
      } else if (result.status === "cancelled") announce("File selection cancelled. No canonical import was committed.");
      else setFailure(result.status === "unavailable" ? "The native file chooser is unavailable. Retry from the installed desktop window when the local service is ready." : "The file could not be prepared. Check its format and local availability, then choose it again. No canonical import was committed.");
    } catch (error) {
      if (live.current && !owner.signal.aborted) setFailure(importFailure(error));
    } finally {
      if (live.current) { setChoosing(false); intake.current = null; chooseButton.current?.focus(); }
    }
  }

  return <div className="ro-page-region" data-import-workspace>
    <header className="page-header"><Typography as="h1" variant="page-title">Ingestion &amp; Reconciliation</Typography>
      <Typography className="page-subtitle">Import references, inspect original values, and review mappings and exclusions before committing anything to the corpus.</Typography></header>
    <Notification tone="info" title="Preview first — researcher decisions stay explicit">Files remain local. Import previews do not create canonical source records or resolve works and versions.</Notification>
    <Panel title="Import records"><div className="ro-form ro-stack">
      <div className="ro-grid import-options">
        <div className="ro-field"><label htmlFor="import-format">Reference format</label><select id="import-format" disabled={choosing} value={options.formatName} onChange={(event) => setOptions({ ...options, formatName: event.currentTarget.value as ImportIntakeOptions["formatName"], encoding: event.currentTarget.value === "csl-json" ? "utf-8" : options.encoding })}>
          <option value="ris">RIS</option><option value="bibtex">BibTeX</option><option value="csl-json">CSL JSON</option><option value="doi-list">DOI list</option><option value="csv">CSV (comma separated)</option>
        </select></div>
        <div className="ro-field"><label htmlFor="import-encoding">Text encoding</label><select id="import-encoding" value={options.encoding} disabled={choosing || options.formatName === "csl-json"} onChange={(event) => setOptions({ ...options, encoding: event.currentTarget.value as ImportIntakeOptions["encoding"] })}>
          <option value="utf-8">UTF-8 (default)</option><option value="cp1252">Windows-1252</option>
        </select></div>
      </div>
      <label className="ro-cluster"><input type="checkbox" checked={options.localUseConfirmed} disabled={choosing} onChange={(event) => setOptions({ ...options, localUseConfirmed: event.currentTarget.checked })} />I confirm I may store and inspect this file locally.</label>
      <p className="field-note">Indexing, derivation, model use, quotation, export and sharing remain unknown—not permitted by this confirmation. Choose an existing local bibliography file; no path typing is required.</p>
      <div className="ro-action-row"><Button ref={chooseButton} tone="primary" disabled={choosing || !options.localUseConfirmed} onClick={() => void choose()}>Choose reference file…</Button>
        {choosing ? <><span role="status">Selecting and retaining the source locally…</span><Button onClick={() => { intake.current?.abort(); announce("Import cancellation requested."); }}>Cancel file intake</Button></> : null}</div>
    </div></Panel>
    {failure ? <Notification tone="danger" title="Import action unavailable">{failure}</Notification> : null}
    <div className="ro-grid import-layout">
      <Panel title="Import batches"><div className="ro-action-row"><Button disabled={loading} onClick={() => void load(after)}>Refresh batches</Button></div>
        {loading ? <p role="status">Loading saved previews…</p> : page?.items.length === 0 ? <p>No accessible previews on this page. Choose a reference file to begin.</p> : null}
        <ul className="import-batches ro-stack">{page?.items.map((item) => <li key={item.previewId}><Button disabled={choosing} aria-pressed={selected?.previewId === item.previewId} onClick={() => setSelected(item)}><span className="ro-wrap-anywhere">{item.sourceName}</span><StatusBadge>{importStatusLabel(item)}</StatusBadge></Button></li>)}</ul>
        <nav className="ro-action-row" aria-label="Import batch pages"><Button disabled={loading || after === null} onClick={() => void load(null)}>First batches</Button><Button disabled={loading || !page || page.complete} onClick={() => page && void load(page.nextAfter)}>Next batches</Button></nav>
      </Panel>
      {selected ? <ImportReviewPane key={selected.previewId} root={project.root} initial={selected} client={client} announce={announce} /> : <Panel title="Select a batch to review"><p>Compare raw fields with normalized candidates, correct mappings, and exclude unwanted records. Saved previews are retained in this project.</p></Panel>}
    </div>
  </div>;
}
