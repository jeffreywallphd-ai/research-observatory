import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createCoreApiClient, decodeConnectorCapabilities, SCHOLARLY_PROVIDER_TERMS, type ConnectorCapabilitiesPage, type CoreApiTransport, type ProjectProjection } from "@research-observatory/contracts/core-api";
import { Button, Notification, Panel, StatusBadge, Typography } from "@research-observatory/ui-components";
import { packagedProjectTransport } from "./ProjectsWorkspace";
import { configureSource, configurationMessage, openSourceTerms, type ConfigurationOutcome, type ScholarlyProvider } from "./sourceConfiguration";
import type { ApplicationWorkspace } from "./workflowNavigationModel";
import { SourceTestPane } from "./SourceTestPane";
import { SourceRequestHistory } from "./SourceRequestHistory";

const SOURCES: readonly { id: ScholarlyProvider; name: string; purpose: string }[] = [
  { id: "openalex", name: "OpenAlex", purpose: "Scholarly metadata search and identifier lookup" },
  { id: "crossref", name: "Crossref", purpose: "DOI metadata and publisher-reported updates" },
  { id: "semantic-scholar", name: "Semantic Scholar", purpose: "Academic graph, citations, references and recommendations" },
  { id: "unpaywall", name: "Unpaywall", purpose: "Open-access locations with reported host and license" },
];
interface SourceManagerProps {
  readonly project: ProjectProjection | null;
  readonly announce: (message: string) => void;
  readonly transport?: CoreApiTransport;
  readonly initialCapabilities?: ConnectorCapabilitiesPage;
  readonly onNavigate?: (workspace: ApplicationWorkspace) => void;
  readonly active?: boolean;
}

export function SourceManagerWorkspace(props: SourceManagerProps): ReactNode {
  const project = props.project;
  if (!project?.open) return <Notification tone="info" title="No project open">Open a local project to manage its scholarly sources.</Notification>;
  if (project.accessMode !== "read-write" || project.compatibilityState !== "compatible") return <Notification tone="warning" title="Source configuration unavailable in read-only mode">Open a compatible project read-write before configuring sources or making requests.</Notification>;
  return <SourceProject key={`${project.projectId}\u0000${project.root}`} {...props} project={project} />;
}

function SourceProject({ project, announce, transport = packagedProjectTransport, initialCapabilities, onNavigate, active = true }: SourceManagerProps & { readonly project: ProjectProjection }): ReactNode {
  const client = useMemo(() => createCoreApiClient(transport), [transport]);
  const initial = initialCapabilities ? decodeConnectorCapabilities(initialCapabilities) : null;
  const [page, setPage] = useState<ConnectorCapabilitiesPage | null>(initial);
  const [loading, setLoading] = useState(initial === null);
  const [failure, setFailure] = useState(false);
  const [busy, setBusy] = useState<ScholarlyProvider | null>(null);
  const [outcome, setOutcome] = useState<ConfigurationOutcome | null>(null);
  const [testing, setTesting] = useState<ScholarlyProvider | null>(null);
  const [inspectionSelection, setInspectionSelection] = useState<{ readonly previewId: string } | null>(null);
  const [termsUnavailable, setTermsUnavailable] = useState(false);
  const live = useRef(true);
  const generation = useRef(0);
  const operation = useRef<AbortController | null>(null);
  const restoreConfigurationFocus = useRef<{ provider: ScholarlyProvider; owner: AbortController } | null>(null);
  const controls = useRef(new Map<ScholarlyProvider, HTMLButtonElement>());
  const testControls = useRef(new Map<ScholarlyProvider, HTMLButtonElement>());

  async function load(): Promise<void> {
    const selected = ++generation.current;
    setLoading(true); setFailure(false);
    try {
      const result = await client.connectorCapabilities();
      if (live.current && selected === generation.current) setPage(result);
    } catch {
      if (live.current && selected === generation.current) { setPage(null); setFailure(true); }
    } finally { if (live.current && selected === generation.current) setLoading(false); }
  }
  useEffect(() => {
    live.current = active;
    if (!active) setTesting(null);
    else if (!operation.current) setBusy(null);
    if (active && initialCapabilities === undefined) void load();
    return () => { live.current = false; generation.current += 1; operation.current?.abort(); };
  }, [client, active]);
  useEffect(() => {
    const pendingFocus = restoreConfigurationFocus.current;
    if (!pendingFocus || busy || loading) return;
    restoreConfigurationFocus.current = null;
    if (active && live.current && !pendingFocus.owner.signal.aborted && !operation.current) {
      controls.current.get(pendingFocus.provider)?.focus();
    }
  }, [active, busy, loading]);

  async function configure(provider: ScholarlyProvider): Promise<void> {
    if (operation.current || !live.current) return;
    const owner = new AbortController(); operation.current = owner;
    setBusy(provider); setOutcome(null);
    try {
      const result = await configureSource(project, provider, owner.signal);
      if (!live.current || owner.signal.aborted) return;
      setOutcome(result); announce(configurationMessage(result));
      await load(); // Read-only status refresh; never retries a save or network request.
    } finally {
      if (operation.current === owner) operation.current = null;
      if (live.current) {
        restoreConfigurationFocus.current = { provider, owner };
        setBusy(null);
      }
    }
  }

  return <div className="ro-page-region" data-source-manager>
    <header className="page-header"><Typography as="h1" variant="page-title">Source Manager</Typography>
      <Typography className="page-subtitle">Configure scholarly metadata and open-access sources; review local imports and project-specific permissions.</Typography>
      <div className="ro-action-row"><Button disabled={!!busy || !onNavigate} onClick={() => onNavigate?.("imports")}>Import and review references</Button><Button disabled={loading || !!busy || !!testing} onClick={() => void load()}>Refresh source status</Button></div>
    </header>
    <Notification tone="info" title="Rights and egress are evaluated per source">Storage, inspection, indexing, model use, sharing and export are separate permissions. Ready configuration is not a successful connection or permission to send research data. Keys and contact details stay in private native settings.</Notification>
    {loading ? <p role="status">Loading source configuration…</p> : null}
    {failure ? <Notification tone="warning" title="Source status unavailable">The local service could not verify configuration. Refresh status when Core is ready; no retrieval or save is retried.</Notification> : null}
    {termsUnavailable ? <Notification tone="warning" title="Policy page could not be opened">The desktop could not open the system browser. The published policy address is shown on the source card; no source request was sent.</Notification> : null}
    {outcome ? <Notification tone={outcome.status === "saved" || outcome.status === "cancelled" ? "info" : "warning"} title={outcome.status === "save-unconfirmed" ? "Save outcome unconfirmed" : "Source configuration"}>{configurationMessage(outcome)}</Notification> : null}
    <section className="ro-stack" aria-labelledby="source-inventory-title"><Typography id="source-inventory-title" as="h2" variant="section-title">Open scholarly sources</Typography>
      <div className="status-grid ro-grid">{SOURCES.map((source) => {
        const entry = page?.items.find((item) => item.providerId === source.id);
        const state = entry?.configuration === "ready" ? "Configured for requests" : entry?.configuration === "not-configured" ? "Contact required" : "Configuration unavailable";
        return <Panel key={source.id} title={source.name}>
          <StatusBadge tone={entry?.configuration === "ready" ? "info" : "warning"}>{state}</StatusBadge>
          <Typography>{source.purpose}</Typography>
          <dl className="ro-key-value"><dt>Adapter</dt><dd>{entry ? `${entry.adapterVersion} · API ${entry.sourceApiVersion ?? "unversioned"}` : "Not verified"}</dd>
            <dt>Operations</dt><dd>{entry?.operations.join(", ") ?? "Not verified"}</dd>
            <dt>Required setting</dt><dd>{source.id === "unpaywall" ? "Contact email; sent only with an approved request" : "None; key or contact is optional"}</dd>
            <dt>Request limits</dt><dd>{entry ? `Maximum ${entry.maximumPageSize} records per page; broker applies bounded retries and provider throttling` : "Not verified"}</dd>
            <dt>Terms and policy</dt><dd><a className="ro-wrap-anywhere" href={SCHOLARLY_PROVIDER_TERMS[source.id]} onClick={(event) => { event.preventDefault(); setTermsUnavailable(false); void openSourceTerms(source.id).catch(() => { if (live.current) setTermsUnavailable(true); }); }}>Open {source.name} policy in your browser</a><p className="ro-wrap-anywhere">{SCHOLARLY_PROVIDER_TERMS[source.id]}</p></dd></dl>
          <div className="ro-action-row"><Button ref={(element) => { if (element) controls.current.set(source.id, element); else controls.current.delete(source.id); }} aria-label={`Configure ${source.name}`} disabled={!!busy || loading || !active || !!testing} onClick={() => void configure(source.id)}>{busy === source.id ? "Configuring…" : "Configure…"}</Button><Button ref={(element) => { if (element) testControls.current.set(source.id, element); else testControls.current.delete(source.id); }} aria-label={`Test ${source.name}`} disabled={!!busy || loading || !active || !!testing || entry?.configuration !== "ready"} onClick={() => setTesting(source.id)}>Test…</Button></div>
        </Panel>;
      })}</div>
    </section>
    {testing && page?.items.find((item) => item.providerId === testing) ? <SourceTestPane key={testing} project={project} provider={page.items.find((item) => item.providerId === testing)!} client={client} announce={announce} active={active} onInspect={(previewId) => setInspectionSelection({ previewId })} onTasks={onNavigate ? () => onNavigate("tasks") : undefined} onClose={() => { const provider = testing; setTesting(null); requestAnimationFrame(() => { if (live.current) testControls.current.get(provider)?.focus(); }); }} /> : null}
    <SourceRequestHistory root={project.root} client={client} active={active} selection={inspectionSelection} />
    <div className="status-grid ro-grid">
      <Panel title="Connection health"><Typography>No provider request is made when this page opens or when settings are saved. Configuration readiness does not establish provider availability, coverage or a last successful call.</Typography><Button disabled={!onNavigate || !!busy} onClick={() => onNavigate?.("tasks")}>Inspect source tasks</Button></Panel>
      <Panel title="Project permissions"><Typography>The accepted Research Intent and current privacy policy must both permit each destination. Every request needs a preview and explicit confirmation. Public metadata does not grant unrestricted downstream rights.</Typography><div className="ro-action-row"><Button disabled={!onNavigate || !!busy} onClick={() => onNavigate?.("intent")}>Review Research Intent</Button><Button disabled={!onNavigate || !!busy} onClick={() => onNavigate?.("settings")}>Review privacy policy</Button><Button disabled={!onNavigate || !!busy} onClick={() => onNavigate?.("models")}>Model &amp; Privacy Center</Button></div></Panel>
      <Panel title="Local sources"><Typography>RIS, BibTeX, CSL JSON, DOI lists and CSV can be selected in a native file chooser, previewed and reviewed. No folder watching or automatic import is enabled.</Typography><Button disabled={!onNavigate || !!busy} onClick={() => onNavigate?.("imports")}>Open import review</Button></Panel>
      <Panel title="Licensed and reference-manager sources"><StatusBadge tone="neutral">Not implemented yet</StatusBadge><Typography>Licensed connectors and direct reference-manager synchronization have separate planned tasks. Exported reference files can be reviewed through the local import route.</Typography></Panel>
      <Panel title="Private technical reports"><StatusBadge tone="neutral">Deferred workflow</StatusBadge><Typography>Report extraction is not available here. Keep private reports local; no scholarly-source permission authorizes report upload or model processing.</Typography></Panel>
      <Panel title="Manuscript drafts"><StatusBadge tone="neutral">Deferred workflow</StatusBadge><Typography>Draft ingestion is not available here. Scholarly-source credentials do not authorize sending private manuscripts to a provider.</Typography></Panel>
    </div>
  </div>;
}
