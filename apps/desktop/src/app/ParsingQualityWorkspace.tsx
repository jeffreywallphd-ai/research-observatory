import { useEffect, useRef, useState, type ReactNode } from "react";
import type { ProjectProjection } from "@research-observatory/contracts/core-api";
import { Button, Notification, Panel, StatusBadge } from "@research-observatory/ui-components";
import type { SourceIdentity } from "./sourceAnchors";
import { newAttachmentId } from "./documentAttachment";
import { ReprocessingPanel } from "./ReprocessingPanel";
import type { DocumentReprocessingPort } from "./documentReprocessing";
import { nativeDocumentCorrectionPort, decodeCorrectionPage, decodeCorrectionQueue, decodeCorrectionDraft, decodeCorrectionAccepted,
  decodeCorrectionImpact, decodeCorrectionQuality, decodeCorrectionTargets, type CorrectionPage, type CorrectionQueue, type CorrectionOperation,
  type CorrectionCommand, type CorrectionImpact, type CorrectionQuality, type CorrectionTargets, type DocumentCorrectionPort, type CorrectionNode } from "./documentCorrections";

export interface QualitySelection { readonly projectId: string; readonly revisionId: string; readonly jobId: string; readonly draftRevisionId: string | null }
interface Props {
  readonly project: ProjectProjection | null; readonly active: boolean; readonly announce: (message: string) => void;
  readonly onReader: (source: SourceIdentity, revision: string, selection: QualitySelection) => void;
  readonly selection?: QualitySelection | null; readonly port?: DocumentCorrectionPort;
  readonly reprocessingPort?: DocumentReprocessingPort;
  readonly onNavigationBlocked?: (blocked: boolean) => void;
}
export function ParsingQualityWorkspace(props: Props): ReactNode {
  if (!props.active || !props.project?.open) return <Notification title="No open project" tone="info">Open a local project to review parsing quality and saved corrections.</Notification>;
  return <QualitySession key={props.project.projectId} {...props} project={props.project} />;
}
function QualitySession({ project, announce, onReader, selection = null, port = nativeDocumentCorrectionPort, reprocessingPort, onNavigationBlocked }: Props & { project: ProjectProjection }): ReactNode {
  const [queue,setQueue]=useState<CorrectionQueue | null>(null), [page,setPage]=useState<CorrectionPage | null>(null), [quality,setQuality]=useState<CorrectionQuality | null>(null);
  const [targets,setTargets]=useState<CorrectionTargets | null>(null), [impact,setImpact]=useState<CorrectionImpact | null>(null);
  const [ops,setOps]=useState<readonly CorrectionOperation[]>([]), [rationale,setRationale]=useState("");
  const [selected,setSelected]=useState(""), [kind,setKind]=useState<CorrectionOperation["op"]>("relabel"), [label,setLabel]=useState(""), [other,setOther]=useState("");
  const [split,setSplit]=useState(""), [work,setWork]=useState(""), [region,setRegion]=useState(["1","0","0","0","0"]);
  const [tab,setTab]=useState("Structure"), [busy,setBusy]=useState(true), [message,setMessage]=useState("Checking current project authority…");
  const [confirmed,setConfirmed]=useState(false), [unknown,setUnknown]=useState<CorrectionCommand | null>(null);
  const [reprocessingBlocked,setReprocessingBlocked]=useState(false);
  const live=useRef(true), owned=useRef(false), generation=useRef(0), heading=useRef<HTMLHeadingElement>(null);
  const draft=page?.draft?.record.state === "draft" ? page.draft : null;
  const dirty=JSON.stringify(ops) !== JSON.stringify(draft?.record.patch.operations ?? []) || rationale !== (draft?.record.rationale ?? "");
  function notify(text: string): void { setMessage(text); announce(text); }
  useEffect(()=> { onNavigationBlocked?.(dirty || busy || Boolean(unknown) || reprocessingBlocked); return ()=>onNavigationBlocked?.(false); },[dirty,busy,unknown,reprocessingBlocked,onNavigationBlocked]);
  async function guarded(action: (current: ()=>boolean)=>Promise<void>): Promise<void> {
    if (owned.current || !live.current) return; owned.current=true; setBusy(true); const ticket=++generation.current;
    const current=(): boolean=>live.current && generation.current === ticket;
    try { await action(current); } catch { if (current()) notify("The exact source, revision, proposal or permission could not be confirmed. Reload saved state before making another decision."); }
    finally { if (current()) { owned.current=false; setBusy(false); } }
  }
  async function load(revision: string, draftRevision: string | null, offset: number, current: ()=>boolean): Promise<void> {
    const next=decodeCorrectionPage(await port.request(project.projectId,{action:"page",revisionId:revision,draftRevisionId:draftRevision,offset}),project.projectId,revision);
    if (!current()) return; if (!next) { setPage(null); throw new Error("correction-unavailable"); }
    setPage(next); setOps(next.draft?.record.state === "draft" ? next.draft.record.patch.operations : []); setRationale(next.draft?.record.state === "draft" ? next.draft.record.rationale : "");
    setImpact(null); setTargets(null); setSelected(""); setConfirmed(false);
    notify(next.currentRevisionId !== next.revisionId ? "This is a retained earlier revision. Reload the current accepted revision to propose or accept corrections." : "Accepted structure loaded. Saved proposals remain separate until explicit acceptance.");
  }
  async function selectJob(jobId: string, revision: string | null, draftRevision: string | null, current: ()=>boolean): Promise<void> {
    setPage(null); setQuality(null); setOps([]); setRationale(""); setImpact(null); setConfirmed(false);
    const report=decodeCorrectionQuality(await port.request(project.projectId,{action:"quality",jobId}),project.projectId,jobId);
    if (!current()) return; if (!report) throw new Error("correction-quality-unavailable"); setQuality(report);
    if (revision) { await load(revision,draftRevision,0,current); } else notify("Quality observations are shown below. This parse has no accepted structure to correct. Inspect or accept its candidate from Task Center first.");
  }
  useEffect(()=> {
    live.current=true; heading.current?.focus();
    void guarded(async current=> {
      const q=decodeCorrectionQueue(await port.request(project.projectId,{action:"queue",afterJobId:null}),project.projectId);
      if (!current()) return; if (!q) throw new Error("correction-queue-unavailable"); setQueue(q);
      if (selection?.projectId === project.projectId) await selectJob(selection.jobId,selection.revisionId,selection.draftRevisionId,current);
      else notify(q.items.length ? "Choose a retained parse to inspect its quality and corrections." : "No retained parsing jobs are available in this project. Import a permitted source and process it in Task Center.");
    });
    return ()=> { live.current=false; generation.current+=1; owned.current=false; };
  },[project.projectId,port]);
  const node=page?.nodes.find(n=>n.nodeId === selected), editable=Boolean(page && page.currentRevisionId === page.revisionId && !busy && !unknown && !reprocessingBlocked);
  function add(): void {
    if (!node?.expectedNodeSha256 || !editable || ops.length >= 32) return;
    const base={nodeId:node.nodeId,expectedNodeSha256:node.expectedNodeSha256}; let op: CorrectionOperation | null=null;
    if (kind === "relabel" && label.trim() && Array.from(label).length <= 160) op={...base,op:kind,label};
    else if (kind === "reorder") op={...base,op:kind,beforeNodeId:other || null};
    else if (kind === "split" && /^\d+$/u.test(split) && node.textStart !== null && node.textEnd !== null && Number(split) > node.textStart && Number(split) < node.textEnd) op={...base,op:kind,at:Number(split)};
    else if (kind === "merge") { const n=page?.nodes.find(n=>n.nodeId === other); if (n?.expectedNodeSha256) op={...base,op:kind,withNodeId:n.nodeId,expectedWithNodeSha256:n.expectedNodeSha256}; }
    else if (kind === "reference-rematch" && node.referenceId && node.expectedReferenceSha256) { const target=targets?.items.find(t=>t.workId === work); if (target) op={...base,op:kind,referenceId:node.referenceId,expectedReferenceSha256:node.expectedReferenceSha256,workId:target.workId,workRevisionId:target.workRevisionId}; }
    else if (kind === "adjust-anchor" && region.every(v=>v.trim() && Number.isFinite(Number(v)) && Number(v) >= 0) && Number.isInteger(Number(region[0])) && Number(region[0]) >= 1 && Number(region[0]) <= 500 && Number(region[3]) >= Number(region[1]) && Number(region[4]) >= Number(region[2])) op={...base,op:kind,locator:{kind:"page-region",pageIndex:Number(region[0])-1,x0:Number(region[1]),y0:Number(region[2]),x1:Number(region[3]),y1:Number(region[4]),unit:"points",origin:"top-left",frame:"unrotated-source-page"}};
    else if (kind === "exclude") op={...base,op:kind};
    if (op) { setOps([...ops,op]); setImpact(null); setConfirmed(false); notify("Proposed operation added locally. Save the proposal to preview it; the accepted revision is unchanged."); }
    else notify("Complete a valid correction for the selected object. Split positions use normalized Unicode codepoints; anchors use the original unrotated page.");
  }
  async function write(command: CorrectionCommand, current: ()=>boolean): Promise<void> {
    let result: unknown;
    try { result=await port.request(project.projectId,command); }
    catch (error) { if (current() && String(error).includes("correction-outcome-unknown")) { setUnknown(command); notify("The command outcome is unknown. Reconcile saved state or retry this exact command; another write is blocked."); return; } throw error; }
    if (!current()) return;
    if (command.action === "accept") {
      const accepted=decodeCorrectionAccepted(result,project.projectId,command.acceptance.expectedCurrentRevisionId);
      if (!accepted || (page && accepted.documentId !== page.documentId)) throw new Error("correction-acceptance-unconfirmed");
      await load(accepted.revisionId,null,0,current); if (current()) notify("Correction explicitly accepted. The new revision and human decision are retained; original source and parser output remain available.");
    } else {
      const saved=decodeCorrectionDraft(result,project.projectId); const expected=command.action === "save" ? command.correction.commandId : command.action === "discard" ? command.discard.commandId : null;
      if (!saved || saved.record.commandId !== expected || (page && saved.record.patch.baseRevisionId !== page.revisionId)) throw new Error("correction-save-unconfirmed");
      await load(saved.record.patch.baseRevisionId,saved.record.revisionId,0,current);
      if (current()) notify(saved.record.state === "discarded" ? "Proposal discarded with a retained human rationale. The accepted revision is unchanged." : "Proposal saved and previewed. The accepted revision and downstream state are unchanged.");
    }
    if (current()) setUnknown(null);
  }
  function save(): void {
    if (!page || !editable || !rationale.trim() || Array.from(rationale).length > 1000) return;
    const command: CorrectionCommand={action:"save",correction:{schemaVersion:"1.0",commandId:newAttachmentId(),draftId:draft?.record.draftId ?? null,expectedDraftRevisionId:draft?.record.revisionId ?? null,patch:{schemaVersion:"1.0",baseRevisionId:page.revisionId,expectedStructureSha256:page.structureSha256,operations:ops},rationale}};
    void guarded(current=>write(command,current));
  }
  function inspectSource(revision: string): void {
    if (!page || busy || dirty || unknown || reprocessingBlocked) { notify("Save or undo local edits and resolve the pending command before opening the Reader."); return; }
    onReader(page.source,revision,{projectId:project.projectId,revisionId:page.revisionId,jobId:page.jobId,draftRevisionId:draft?.record.revisionId ?? null});
  }
  function nodeList(nodes: readonly CorrectionNode[], proposed: boolean): ReactNode {
    return <ol className="quality-node-list">{nodes.map(n=><li key={n.nodeId}><div className="ro-action-row"><strong>{n.label ?? n.kind}</strong><span>{n.kind} · {n.order + 1}</span>{!proposed ? <Button disabled={!editable} aria-pressed={selected === n.nodeId} onClick={()=> {setSelected(n.nodeId);setLabel(n.label ?? "");setOther("");}}>Correct object {n.order + 1}</Button> : <StatusBadge tone="info">Proposed</StatusBadge>}</div><p className="quality-private-text">{n.preview || "No normalized text reported."}</p><p className="small">{n.locator.kind === "page-region" ? `Original page ${n.locator.pageIndex+1}; unrotated points (${n.locator.x0}, ${n.locator.y0})–(${n.locator.x1}, ${n.locator.y1})` : n.locator.kind === "text" ? "Original text locator retained" : `Locator ${n.locator.reason}`}</p></li>)}</ol>;
  }
  const visible=(nodes: readonly CorrectionNode[]): readonly CorrectionNode[]=>nodes.filter(n=> tab === "Anchors" ? true : tab === "Tables & figures" ? ["table","table-cell","figure","caption"].includes(n.kind) : tab === "References" ? n.kind === "reference" : true);
  return <section className="ro-page-region ro-stack parsing-quality-workspace" aria-label="Parsing Quality and Corrections" onKeyDown={e=> {if (e.key === "Escape") {setSelected("");heading.current?.focus();}}}>
    <header className="page-header"><h1 className="ro-typography ro-typography--page-title" tabIndex={-1} ref={heading}>Parsing Quality &amp; Corrections</h1><p className="page-subtitle">Inspect retained observations, propose a correction, and explicitly accept a new document revision.</p></header>
    <p role="status" aria-live="polite">{message}</p>
    <div className="quality-layout"><Panel title="Quality queue"><p>Retained local jobs. Quality observations guide review; they do not verify research claims.</p><ul className="quality-node-list">{queue?.items.map(item=><li key={item.jobId}><Button disabled={busy || dirty || Boolean(unknown) || reprocessingBlocked} onClick={()=>void guarded(current=>selectJob(item.jobId,item.revisionId,null,current))}>Inspect parse {item.jobId}</Button><p>{item.revisionId ? "Accepted structure available" : "No accepted structure"}</p></li>)}</ul>
      <Button disabled={busy || dirty || Boolean(unknown) || reprocessingBlocked} onClick={()=>void guarded(async current=> {const q=decodeCorrectionQueue(await port.request(project.projectId,{action:"queue",afterJobId:null}),project.projectId);if(current() && q) {setQueue(q);notify("Quality queue refreshed under current authority.");}})}>Refresh quality queue</Button>
      {queue?.nextAfterJobId ? <Button disabled={busy || dirty || Boolean(unknown) || reprocessingBlocked} onClick={()=>void guarded(async current=> {const q=decodeCorrectionQueue(await port.request(project.projectId,{action:"queue",afterJobId:queue.nextAfterJobId}),project.projectId);if(!current()) return;if(!q) {setQueue(null);throw new Error("correction-queue-unavailable");}setQueue(q);})}>Next jobs</Button> : null}</Panel>
      <div className="ro-stack">{quality ? <Panel title="Retained quality observations"><p>Availability: {quality.assessment.availability}. {quality.assessment.reviewRequired ? "Human review required" : "Human inspection available"}. Scholarly claims remain unverified.</p><div className="quality-dimensions">{Object.entries(quality.assessment.dimensions).map(([name,d])=><div key={name}><h3>{name.replace(/([A-Z])/gu," $1")}</h3><p>{d.state}</p><dl>{Object.entries(d).filter(([key])=>key !== "state" && key !== "parserObservation" && key !== "codes").map(([key,value])=><div key={key}><dt>{key.replace(/([A-Z])/gu," $1")}</dt><dd>{value === null ? "Not reported" : String(value)}</dd></div>)}</dl>{Array.isArray(d.codes) ? <p>{d.codes.join(", ") || "No reported warning codes"}</p> : null}</div>)}</div><p>{quality.assessment.reviewReasons.join(", ") || "No triage reasons reported."}</p></Panel> : null}
      {page ? <><Panel title="Structure and source checks"><p>Exact accepted revision: <span className="quality-id">{page.revisionId}</span></p><div className="ro-action-row">{["Structure","Anchors","Tables & figures","References","Corrections"].map(name=><Button key={name} aria-pressed={tab === name} onClick={()=>setTab(name)}>{name}</Button>)}</div>
        <div className="quality-comparison"><section aria-label="Accepted structure"><h3>Accepted structure</h3>{nodeList(visible(page.nodes),false)}</section><section aria-label="Proposed structure"><h3>Proposed structure</h3>{draft ? nodeList(visible(page.previewNodes),true) : <p>No saved proposal for this revision.</p>}</section></div>
        {page.nextOffset !== null ? <Button disabled={busy || dirty || Boolean(unknown) || reprocessingBlocked} onClick={()=>void guarded(current=>load(page.revisionId,draft?.record.revisionId ?? null,page.nextOffset!,current))}>Next objects</Button> : null}
        <Button disabled={busy || dirty || Boolean(unknown) || reprocessingBlocked} onClick={()=>void guarded(current=>load(page.currentRevisionId,null,0,current))}>Reload current accepted revision</Button>
        <Button disabled={busy || dirty || Boolean(unknown) || reprocessingBlocked} onClick={()=>inspectSource(page.revisionId)}>Open accepted revision in Reader</Button><Button disabled={busy || dirty || Boolean(unknown) || reprocessingBlocked} onClick={()=>inspectSource(page.machineRevisionId)}>Inspect original parser revision</Button>
        {page.acceptedReferenceMatches.map(m=><p key={m.referenceId}>Human accepted reference target: <span className="quality-id">{m.workId}</span> at revision <span className="quality-id">{m.workRevisionId}</span>. Matching assertions and scholarly verification remain separate.</p>)}
      </Panel>
      {node ? <Panel title={`Correct object ${node.order+1}`}><div className="quality-fields"><label>Correction type<select value={kind} disabled={!editable} onChange={e=>setKind(e.currentTarget.value as CorrectionOperation["op"])}>{["relabel","reorder","split","merge","reference-rematch","adjust-anchor","exclude"].map(value=><option key={value} value={value}>{value}</option>)}</select></label>
        {kind === "relabel" ? <label>Human section label<input value={label} maxLength={320} onChange={e=>setLabel(e.currentTarget.value)} /></label> : null}
        {kind === "reorder" || kind === "merge" ? <label>{kind === "reorder" ? "Move before sibling" : "Merge with next sibling"}<select value={other} onChange={e=>setOther(e.currentTarget.value)}><option value="">{kind === "reorder" ? "End of sibling group" : "Choose a sibling"}</option>{page.nodes.filter(n=>n.nodeId !== node.nodeId && n.parentId === node.parentId).map(n=><option key={n.nodeId} value={n.nodeId}>{n.order+1}: {n.preview || n.kind}</option>)}</select></label> : null}
        {kind === "split" ? <label>Split at normalized codepoint (between {node.textStart ?? "unavailable"} and {node.textEnd ?? "unavailable"})<input inputMode="numeric" value={split} onChange={e=>setSplit(e.currentTarget.value)} /></label> : null}
        {kind === "reference-rematch" ? <><Button disabled={!editable || !node.referenceId} onClick={()=>void guarded(async current=> {const t=decodeCorrectionTargets(await port.request(project.projectId,{action:"targets",afterWorkId:null}),project.projectId); if(!current()) return;if(!t) {setTargets(null);throw new Error("correction-targets-unavailable");}setTargets(t);})}>Load current permitted Work targets</Button><label>Human reference target<select value={work} onChange={e=>setWork(e.currentTarget.value)}><option value="">Choose a Work</option>{targets?.items.map(t=><option key={t.workId} value={t.workId}>{t.title}</option>)}</select></label>{targets?.nextAfterWorkId ? <Button disabled={!editable} onClick={()=>void guarded(async current=> {const t=decodeCorrectionTargets(await port.request(project.projectId,{action:"targets",afterWorkId:targets.nextAfterWorkId}),project.projectId);if(!current()) return;if(!t) {setTargets(null);throw new Error("correction-targets-unavailable");}setTargets(t);setWork("");})}>Next Work targets</Button> : null}<p>A human target choice is not identifier verification.</p></> : null}
        {kind === "adjust-anchor" ? <>{["Original page number","Left (points)","Top (points)","Right (points)","Bottom (points)"].map((name,index)=><label key={name}>{name}<input value={region[index]} inputMode="decimal" onChange={e=>setRegion(region.map((v,i)=>i === index ? e.currentTarget.value : v))} /></label>)}<p>The saved source page geometry must admit this rectangle. Rotated-screen coordinates are not accepted.</p></> : null}
        {kind === "exclude" ? <p>Exclude this corrupted region from the corrected structure. Original text and prior history remain retained.</p> : null}</div><Button disabled={!editable || ops.length >= 32} onClick={add}>Add proposed correction</Button></Panel> : null}
      <div className="quality-comparison"><Panel title="Manual correction ledger"><p>{ops.length} proposed operations. {dirty ? "Unsaved local edits" : "Saved state"}.</p><ol>{ops.map((op,i)=><li key={i}>{op.op} · <span className="quality-id">{op.nodeId}</span></li>)}</ol><label>Correction rationale<textarea value={rationale} maxLength={2000} disabled={!editable} onChange={e=> {setRationale(e.currentTarget.value);setConfirmed(false);}} /></label><div className="ro-action-row"><Button disabled={!editable || !dirty || !rationale.trim() || Array.from(rationale).length > 1000} onClick={save}>Save proposal and preview</Button><Button disabled={!editable || !ops.length} onClick={()=> {setOps(ops.slice(0,-1));setImpact(null);setConfirmed(false);}}>Undo last proposed operation</Button><Button disabled={busy || Boolean(unknown) || reprocessingBlocked || !dirty} onClick={()=> {setOps(draft?.record.patch.operations ?? []);setRationale(draft?.record.rationale ?? "");setConfirmed(false);notify("Unsaved local edits undone. The saved proposal is unchanged.");}}>Undo unsaved edits</Button></div>
        {draft ? <p>Saved by <span className="quality-id">{draft.record.authoredBy}</span> at {draft.record.authoredAt}. Proposal revision <span className="quality-id">{draft.record.revisionId}</span>.</p> : null}
        {page.acceptedDecision ? <><p>Revision accepted by <span className="quality-id">{page.acceptedBy}</span> at {page.acceptedAt}.</p><p>Accepted proposal authored by <span className="quality-id">{page.acceptedDecision.record.authoredBy}</span>: {page.acceptedDecision.record.rationale} ({page.acceptedDecision.record.authoredAt}).</p></> : null}
        {page.drafts.length ? <label>Retained proposal history<select value={page.draft?.record.revisionId ?? ""} disabled={busy || dirty || Boolean(unknown) || reprocessingBlocked} onChange={e=> {const d=page.drafts.find(d=>d.draftRevisionId === e.currentTarget.value);if(d) void guarded(current=>load(d.baseRevisionId,d.draftRevisionId,0,current));}}><option value="">Select a saved proposal</option>{page.drafts.map(d=><option value={d.draftRevisionId} key={d.draftRevisionId}>{d.draftRevisionId}</option>)}</select></label> : null}
        {draft ? <Button disabled={!editable || dirty || !rationale.trim()} onClick={()=>void guarded(current=>write({action:"discard",discard:{schemaVersion:"1.0",commandId:newAttachmentId(),draftRevisionId:draft.record.revisionId,confirmationSha256:draft.confirmationSha256,rationale}},current))}>Discard saved proposal</Button> : null}
      </Panel><Panel title="Correction impact"><p>Saving and previewing do not update accepted structure or downstream state.</p><Button disabled={!editable || dirty || !draft || !draft.record.patch.operations.length} onClick={()=>void guarded(async current=> {if(!draft) return;const p=decodeCorrectionImpact(await port.request(project.projectId,{action:"impact",draftRevisionId:draft.record.revisionId}),project.projectId,draft);if(!current()) return;if(!p) {setImpact(null);setConfirmed(false);throw new Error("correction-impact-unavailable");}{setImpact(p);setConfirmed(false);notify("Current dependency impact preview loaded. Acceptance will recheck the graph and authority.");}})}>Preview current impact</Button>
        {impact ? <><dl><dt>Affected downstream revisions</dt><dd>{impact.affectedCount}</dd><dt>Informational relations</dt><dd>{impact.informationalCount}</dd><dt>Legacy relations with unreported impact</dt><dd>{impact.legacyUnreportedCount}</dd></dl><ul>{impact.items.map(item=><li key={item.revisionId}>{item.kind}: {item.disposition} · <span className="quality-id">{item.revisionId}</span></li>)}</ul>{impact.truncated ? <p>Only the first 20 relations are displayed.</p> : null}<p>Prospective impact. The current graph and permissions are checked again during acceptance. Recalculation is a separate action.</p><label><input type="checkbox" checked={confirmed} disabled={!editable || dirty} onChange={e=>setConfirmed(e.currentTarget.checked)} />I accept this exact saved proposal as a new document revision, with the recorded rationale and downstream impact.</label></> : null}
        <Button disabled={!editable || dirty || !draft || !impact || !confirmed || !draft.record.patch.operations.length} onClick={()=> {if(draft) void guarded(current=>write({action:"accept",acceptance:{schemaVersion:"1.0",commandId:newAttachmentId(),draftRevisionId:draft.record.revisionId,expectedCurrentRevisionId:page.revisionId,confirmationSha256:draft.confirmationSha256,decision:"accept-correction"}},current));}}>Accept exact saved correction</Button>
      </Panel></div></> : null}
      {unknown ? <Panel title="Reconcile pending command"><p>An issued command may have completed. Its exact identity is retained in this session.</p><Button disabled={busy} onClick={()=>void guarded(current=>write(unknown,current))}>Retry exact pending command</Button><Button disabled={busy || !page} onClick={()=>void guarded(async current=> {if(page) await load(page.currentRevisionId,null,0,current);if(current()) notify("Saved state reconciled. The exact pending command remains available for a definitive idempotent outcome.");})}>Reconcile saved state</Button></Panel> : null}
      <ReprocessingPanel projectId={project.projectId} availableRevisions={[...new Set([page?.currentRevisionId,...(queue?.items.map(item=>item.revisionId) ?? [])].filter((revision): revision is string=>Boolean(revision)))]}
        correctionBlocked={busy || dirty || Boolean(unknown)} announce={announce} onBlocked={setReprocessingBlocked} port={reprocessingPort}
        onAccepted={async (comparison,accepted)=> {await guarded(current=>selectJob(comparison.jobId,accepted.revisionId,null,current));}} />
      </div></div>
  </section>;
}
