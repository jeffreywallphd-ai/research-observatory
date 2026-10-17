import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createCoreApiClient, type CoreApiTransport, type ProjectProjection, type SearchDocumentTarget,
  type SearchExplanation, type SearchJob, type SearchPage, type SearchQueryValidation, type SearchRunCommand,
  type SearchSnippet } from "@research-observatory/contracts/core-api";
import { Button, Field, Notification, Panel, StatusBadge } from "@research-observatory/ui-components";
import { packagedProjectTransport } from "./ProjectsWorkspace";
import { corpusReportCommandId } from "./CorpusCanvasWorkspace";
import { codepointRangeToUtf16 } from "./sourceAnchors";

// Protected, bounded session context. The parent owns this across Reader visits;
// it is never written to browser storage or restored after lock/project change.
export interface SearchWorkspaceState {
  readonly scopeKey: string;
  readonly query: string;
  readonly yearFrom: string;
  readonly yearTo: string;
  readonly validation: SearchQueryValidation | null;
  readonly savedDraft: Readonly<{ query: string; yearFrom: string; yearTo: string }> | null;
  readonly job: SearchJob | null;
  readonly pendingRequest: SearchRunCommand | null;
  readonly page: SearchPage | null;
  readonly explanation: SearchExplanation | null;
  readonly focusItem: string | null;
  readonly scrollY: number;
}
export const emptySearchState = (scopeKey: string): SearchWorkspaceState => ({
  scopeKey, query:"", yearFrom:"", yearTo:"", validation:null, savedDraft:null, job:null, pendingRequest:null,
  page:null, explanation:null, focusItem:null, scrollY:0,
});

export function SearchSnippetText({ snippet }: {readonly snippet: SearchSnippet}): ReactNode {
  const parts: ReactNode[] = [];
  let start = 0;
  for (const span of snippet.highlights) {
    const range = codepointRangeToUtf16(snippet.text, span);
    parts.push(snippet.text.slice(start, range.start), <mark key={span.start}>{snippet.text.slice(range.start, range.end)}</mark>);
    start = range.end;
  }
  parts.push(snippet.text.slice(start));
  return <><p className="anchor-passage-text">{parts}</p>{snippet.truncated ? <small>Preview truncated; inspect the exact source for context.</small> : null}</>;
}

interface Props {
  readonly project: ProjectProjection | null;
  readonly scopeKey: string | null;
  readonly state: SearchWorkspaceState | null;
  readonly onStateChange: (state: SearchWorkspaceState) => void;
  readonly announce: (message: string) => void;
  readonly onOpenSource: (target: SearchDocumentTarget, current: () => boolean) => Promise<boolean>;
  readonly active?: boolean;
  readonly transport?: CoreApiTransport;
}
const pending = (job: SearchJob): boolean => !["succeeded","failed","cancelled"].includes(job.state);
const sameExecution = (left: SearchPage["execution"], right: SearchPage["execution"]): boolean =>
  left.revisionId === right.revisionId && left.inputSha256 === right.inputSha256
    && left.resultSha256 === right.resultSha256 && left.generationId === right.generationId;

export function SearchWorkspace(props: Props): ReactNode {
  if (!props.project?.open || props.project.compatibilityState !== "compatible" || !props.scopeKey) return <Panel title="Search Studio">
    <p>Open a protected project with a current accepted Research Intent to search lawful local records.</p></Panel>;
  return <SearchSession key={props.scopeKey} {...props} project={props.project} scopeKey={props.scopeKey} />;
}

function SearchSession({ project, scopeKey, state: retained, onStateChange, announce, onOpenSource,
  active=true, transport=packagedProjectTransport }: Props & {project: ProjectProjection; scopeKey:string}): ReactNode {
  const [state, setState] = useState(() => retained?.scopeKey === scopeKey ? retained : emptySearchState(scopeKey));
  const [busy, setBusy] = useState(false), [checking, setChecking] = useState(Boolean(state.page));
  const [notice, setNotice] = useState("Draft. Validation and preview do not execute retrieval.");
  const [failure, setFailure] = useState(false);
  const client = useMemo(() => createCoreApiClient(transport), [transport]);
  const value = useRef(state), generation = useRef(0), live = useRef(true), enabled = useRef(active);
  const heading = useRef<HTMLHeadingElement>(null), explanationHeading = useRef<HTMLHeadingElement>(null);
  const wasActive = useRef(active), selectedFocus = useRef<string | null>(null);
  enabled.current = active;
  const update = (patch: Partial<SearchWorkspaceState>): SearchWorkspaceState => {
    const next = {...value.current, ...patch}; value.current = next; setState(next); onStateChange(next); return next;
  };
  const current = (ticket:number): boolean => live.current && enabled.current && generation.current === ticket;
  const notify = (message:string): void => { setNotice(message); announce(message); };
  const fail = (): void => {
    update({page:null, explanation:null, focusItem:null}); setChecking(false); setFailure(true); setBusy(false);
    notify("Search inputs or source access could not be confirmed. Review the current project and rights, then run again. No replacement result was opened.");
    requestAnimationFrame(() => heading.current?.focus());
  };
  const address = (job:SearchJob) => ({root:project.root, projectId:project.projectId, jobId:job.jobId});

  async function pageFor(job:SearchJob, after:string|null, ticket:number, restore=false): Promise<void> {
    const previous = value.current.page;
    const result = await client.pageLexicalSearch({...address(job), after, limit:50});
    if (!current(ticket)) return;
    if (previous && !sameExecution(previous.execution, result.execution)) throw new Error("search-run-changed");
    update({page:result, explanation:null}); setChecking(false); setFailure(false);
    notify(`${result.execution.resultCount} lawful lexical results. Showing ${result.hits.length ? result.startPosition+1 : 0}–${result.startPosition+result.hits.length}. Semantic unqualified; rerank not run.`);
    requestAnimationFrame(() => {
      if (!current(ticket)) return;
      const item = restore ? value.current.focusItem : null;
      const control = item ? document.getElementById(`search-source-${item}`) : null;
      if (restore) window.scrollTo({top:value.current.scrollY});
      if (control instanceof HTMLButtonElement) control.focus({preventScroll:true});
      else if (restore) { heading.current?.focus(); if (item) notify("The exact selected result is no longer in this page. The search heading has focus."); }
    });
  }

  async function refresh(ticket:number, restore=false): Promise<void> {
    const job = value.current.job;
    if (!job) return;
    const result = await client.inspectLexicalSearch(address(job));
    if (!current(ticket)) return;
    if (result.commandId !== job.commandId || result.workflowRunId !== job.workflowRunId) throw new Error("search-job-changed");
    setFailure(false);
    update({job:result});
    if (result.state === "succeeded") await pageFor(result, value.current.page?.afterCursor ?? null, ticket, restore);
    else { setChecking(false); notify(`Search ${result.state}. Attempts: ${result.attemptCount}.${result.diagnosticCode ? " Review Task Center for the retained failure." : ""}`); }
  }

  useEffect(() => {
    live.current = true;
    if (active && value.current.job) {
      const ticket = ++generation.current; setChecking(Boolean(value.current.page));
      void refresh(ticket, true).catch(() => { if (current(ticket)) fail(); });
    } else heading.current?.focus();
    return () => { live.current = false; generation.current += 1; };
    // The session key owns project/Intent/selection identity; API client is stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client]);

  useEffect(() => {
    if (active === wasActive.current) return;
    wasActive.current = active;
    const ticket = ++generation.current; setBusy(false);
    if (active && value.current.job) {
      setChecking(true); void refresh(ticket,true).catch(() => { if (current(ticket)) fail(); });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  useEffect(() => {
    if (!active || !state.job || !pending(state.job) || busy) return;
    const timer = window.setTimeout(() => {
      const ticket = generation.current;
      void refresh(ticket).catch(() => { if (current(ticket)) fail(); });
    }, 500);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.job, active, busy]);

  useEffect(() => {
    const deadline = state.page?.execution.expiresAt;
    if (!deadline || !active) return;
    const remaining = Date.parse(deadline)-Date.now();
    const timer = window.setTimeout(() => { generation.current += 1; fail(); }, Math.max(0,Math.min(remaining,2_147_483_647)));
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.page, active]);

  async function action(operation:(ticket:number)=>Promise<void>):Promise<void> {
    if (busy || !enabled.current) return;
    const ticket = ++generation.current; setBusy(true); setFailure(false);
    try { await operation(ticket); } catch { if (current(ticket)) fail(); }
    finally { if (current(ticket)) setBusy(false); }
  }
  function filters(): {yearFrom:number|null; yearTo:number|null} {
    const year = (raw:string):number|null => {
      if (!raw) return null;
      if (!/^\d{1,4}$/u.test(raw) || Number(raw)<1) throw new Error("search-year-invalid");
      return Number(raw);
    };
    const result = {yearFrom:year(value.current.yearFrom), yearTo:year(value.current.yearTo)};
    if (result.yearFrom !== null && result.yearTo !== null && result.yearFrom>result.yearTo) throw new Error("search-year-order-invalid");
    return result;
  }
  async function validate(ticket:number):Promise<boolean> {
    const query = value.current.query;
    const result = await client.validateLexicalQuery({query});
    if (!current(ticket)) return false;
    update({validation:result});
    if (!result.valid) { notify(`Invalid query: ${result.diagnostic?.code ?? "unsupported syntax"}, line ${result.diagnostic?.line}, column ${result.diagnostic?.column}.`); return false; }
    filters(); notify("Draft validated. The displayed normalized query has no source translation loss. No search has run."); return true;
  }

  const shown = !checking && !failure ? state.page : null;
  return <section className="ro-page-region ro-stack" data-search-workspace="true" aria-labelledby="search-heading">
    <h1 id="search-heading" tabIndex={-1} ref={heading}>Search Studio</h1>
    <p>Search lawful local records, inspect exact sources, and keep the executed query and ranking visible.</p>
    <Panel title="Source selection and query builder">
      <div className="ro-form">
      <Field id="search-scope" label="Execution scope" input={{value:"Local lawful project records",readOnly:true}} />
      <label htmlFor="search-query">Query draft</label>
      <textarea className="ro-search-query" id="search-query" rows={4} maxLength={8192} value={state.query}
        aria-describedby="search-query-help" disabled={busy}
        onChange={event => update({query:event.target.value,validation:null})} />
      <p id="search-query-help">Use title, abstract, full-text, authors, venue, identifiers, tags, decisions and year fields; phrases, AND, OR and NOT. Query text is never SQL.</p>
      <div className="ro-action-row">
        <Field id="search-year-from" label="Year from" input={{value:state.yearFrom, inputMode:"numeric",maxLength:4,disabled:busy,onChange:event=>update({yearFrom:event.target.value})}} />
        <Field id="search-year-to" label="Year to" input={{value:state.yearTo,inputMode:"numeric",maxLength:4,disabled:busy,onChange:event=>update({yearTo:event.target.value})}} />
      </div>
      <div className="ro-action-row">
        <Button disabled={busy || !state.query} onClick={()=>void action(async ticket=>{await validate(ticket);})}>Validate / preview draft</Button>
        <Button disabled={busy || !state.query} onClick={()=>{update({savedDraft:{query:state.query,yearFrom:state.yearFrom,yearTo:state.yearTo}});notify("Draft kept for this authorized session. Retrieval has not run.");}}>Keep draft for this session</Button>
        {state.savedDraft ? <Button disabled={busy} onClick={()=>update({...state.savedDraft!,validation:null})}>Restore session draft</Button> : null}
        <Button tone="primary" disabled={busy || !state.query || Boolean(state.pendingRequest) || Boolean(state.job && pending(state.job))} onClick={()=>void action(async ticket=>{
          if (!await validate(ticket)) return;
          const request = {root:project.root,projectId:project.projectId,commandId:corpusReportCommandId(null),query:value.current.query,filters:filters()};
          update({page:null,explanation:null,focusItem:null,job:null,pendingRequest:request});
          const job = await client.executeLexicalSearch(request);
          if (current(ticket)) {
            update({job,pendingRequest:null});notify(`Search ${job.state}; durable job ${job.jobId}.`);
            if(job.state==="succeeded")await pageFor(job,null,ticket);
          }
        })}>Run search</Button>
        {state.pendingRequest ? <Button disabled={busy} onClick={()=>void action(async ticket=>{
          const job=await client.executeLexicalSearch(value.current.pendingRequest!);
          if(current(ticket)){
            update({job,pendingRequest:null});notify(`Exact search command reconciled: ${job.state}.`);
            if(job.state==="succeeded")await pageFor(job,null,ticket);
          }
        })}>Retry same search command</Button> : null}
        <Button disabled={busy || !state.job || !pending(state.job)} onClick={()=>void action(async ticket=>{
          const job=value.current.job!; update({page:null,explanation:null,focusItem:null});
          notify("Cancellation requested. Waiting for the existing worker to drain.");
          const result=await client.cancelLexicalSearch(address(job));
          if(current(ticket)){update({job:result});notify(`Search ${result.state}; cancellation retains immutable attempts.`);}
        })}>Cancel search</Button>
        {state.job ? <Button disabled={busy} onClick={()=>void action(ticket=>refresh(ticket))}>Recheck search status</Button> : null}
      </div>
      {state.pendingRequest ? <p>Run acknowledgement unconfirmed. Retry retains command <code>{state.pendingRequest.commandId}</code> and its exact query <code>{state.pendingRequest.query}</code>; editing a draft cannot change that request.</p> : null}
      {state.validation?.valid ? <><h3>Normalized query preview</h3><pre>{state.validation.normalizedQuery}</pre><p>Local grammar: no source translation loss. Validation does not confirm source rights or index readiness.</p></> : null}
      <p role="status">{notice}</p>
      {failure ? <Notification title="Search inaccessible" tone="warning">The previous page and explanation were cleared. Recheck source rights before another execution.</Notification> : null}
      </div>
    </Panel>
    <Panel title="Executed components and immutable run">
      <StatusBadge tone="info">Lexical only</StatusBadge> <StatusBadge tone="warning">Semantic unqualified</StatusBadge> <StatusBadge tone="info">Rerank not run</StatusBadge>
      <p>Weighted BM25 relevance with stable item-ID ties. Scores are method-specific, not probabilities. Filters affect membership, not the lawful statistical universe.</p>
      {state.job ? <p>Job <code>{state.job.jobId}</code>: {state.job.state}; attempts {state.job.attemptCount}.</p> : <p>No retrieval has run.</p>}
      {shown ? <><p>Run <code>{shown.execution.searchRunId}</code>; revision <code>{shown.execution.revisionId}</code>; generation <code>{shown.execution.generationId}</code>; source watermark {shown.execution.sourceWatermark}.</p>
        <p>Executed query: <code>{shown.execution.originalQuery}</code>. Normalized: <code>{shown.execution.normalizedQuery}</code>.</p>
        <p>Executed year filter: {shown.execution.filters.yearFrom ?? "unbounded"}–{shown.execution.filters.yearTo ?? "unbounded"}. Method: {shown.execution.rankingVersion}.</p></> : null}
      <p>Expansion and search-tree editing are unavailable. A query never changes corpus membership.</p>
    </Panel>
    <Panel title="Source-first results">
      {checking ? <p role="status">Checking this exact saved page under current authority…</p> : null}
      {shown ? <><p>{shown.execution.resultCount} results; {shown.hits.length ? shown.startPosition+1 : 0}–{shown.startPosition+shown.hits.length} shown.</p>
        <div className="ro-table-region"><table className="ro-table"><caption>Lawful lexical search results</caption>
          <thead><tr><th scope="col">Rank and Work/version</th><th scope="col">Match and score</th><th scope="col">Source inspection</th></tr></thead>
          <tbody>{shown.hits.map(hit=><tr key={hit.itemId}>
            <td>{hit.position}. {hit.title}{hit.titleTruncated ? " (title truncated)" : ""}<p>Year: {hit.year ?? "Unknown"}</p><code>{hit.workId}</code><p>Revision <code>{hit.workRevisionId}</code></p></td>
            <td>{hit.snippet ? <><p>Matched field: {hit.snippet.field}</p><SearchSnippetText snippet={hit.snippet} /></> : <p>No positive text snippet; membership may derive from filters or NOT.</p>}<p>Lexical score: {hit.score}</p>
              <Button disabled={busy} onClick={()=>void action(async ticket=>{const result=await client.explainLexicalSearch({...address(state.job!),itemId:hit.itemId});if(current(ticket)){if(!sameExecution(shown.execution,result.execution))throw new Error("search-explanation-stale");selectedFocus.current=hit.itemId;update({explanation:result});requestAnimationFrame(()=>explanationHeading.current?.focus());}})}>Explain rank {hit.position}</Button></td>
            <td><Button id={`search-source-${hit.itemId}`} disabled={busy || !hit.source} onClick={()=>void action(async ticket=>{
              const fresh=await client.pageLexicalSearch({...address(state.job!),after:shown.afterCursor,limit:50});
              if(!current(ticket))return;
              if(!sameExecution(shown.execution,fresh.execution)
                || JSON.stringify(fresh.hits.find(value=>value.itemId===hit.itemId)?.source)!==JSON.stringify(hit.source)) throw new Error("search-source-changed");
              update({focusItem:hit.itemId,scrollY:window.scrollY});
              if(!await onOpenSource(hit.source!,()=>current(ticket))){if(current(ticket))fail();}
            })}>Inspect source for rank {hit.position}</Button><p>{hit.source ? hit.source.locationState === "contained-text-selection" ? "Exact source selection; Reader checks its own permission." : "Exact accepted revision; preview has no contained text anchor." : "No accepted document source for this metadata match."}</p></td>
          </tr>)}</tbody></table></div>
        <div className="ro-action-row"><Button disabled={busy || shown.startPosition===0} onClick={()=>void action(ticket=>pageFor(state.job!,null,ticket))}>First results</Button>
          <Button disabled={busy || !shown.nextCursor} onClick={()=>void action(ticket=>pageFor(state.job!,shown.nextCursor,ticket))}>Next results</Button>
          <Button disabled={busy} onClick={()=>void action(ticket=>refresh(ticket))}>Recheck current access</Button></div></> : !checking ? <p>No currently confirmed result page.</p> : null}
      {shown && state.explanation ? <section aria-labelledby="search-explanation" onKeyDown={event=>{if(event.key==="Escape"){update({explanation:null});document.getElementById(`search-source-${selectedFocus.current}`)?.closest("tr")?.querySelector("button")?.focus();}}}>
        <h2 id="search-explanation" tabIndex={-1} ref={explanationHeading}>Ranking explanation</h2><p>Total weighted BM25 score: {state.explanation.score}. Repeated identical leaves count once; negative/filter clauses contribute membership only.</p>
        <ul>{state.explanation.components.map(component=><li key={component.leafSha256}>{component.matchKind}; field {component.field ?? "all fields"}; contribution {component.score}; leaf <code>{component.leafSha256}</code>.</li>)}</ul>
        <Button onClick={()=>{update({explanation:null});document.getElementById(`search-source-${selectedFocus.current}`)?.closest("tr")?.querySelector("button")?.focus();}}>Close explanation</Button></section> : null}
    </Panel>
    <Panel title="Coverage and human decisions"><p>Population, unjudged records, language/source overlap and full-text coverage denominators: Unknown. A result count does not establish systematic completeness or scientific relevance.</p><p>Review exact sources before separate corpus or screening decisions. Remote sources are managed through Source Manager.</p></Panel>
  </section>;
}
