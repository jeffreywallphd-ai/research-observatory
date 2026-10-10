import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button, Panel, StatusBadge } from "@research-observatory/ui-components";
import { newAttachmentId } from "./documentAttachment";
import { decodeReprocessingAccepted, decodeReprocessingBatch, decodeReprocessingPage, decodeReprocessingQueue, nativeDocumentReprocessingPort,
  type DocumentReprocessingPort, type ReprocessingAccepted, type ReprocessingBatch, type ReprocessingCommand, type ReprocessingDifference,
  type ReprocessingItem, type ReprocessingMapping, type ReprocessingNode, type ReprocessingPage, type ReprocessingQueue, type ReprocessingAssessment } from "./documentReprocessing";

interface Props {
  readonly projectId: string; readonly availableRevisions: readonly string[]; readonly correctionBlocked: boolean;
  readonly announce: (message: string)=>void; readonly onBlocked: (blocked: boolean)=>void;
  readonly onAccepted: (page: ReprocessingPage, accepted: ReprocessingAccepted)=>Promise<void>;
  readonly port?: DocumentReprocessingPort | undefined;
}
interface Pending { readonly command: ReprocessingCommand; readonly batch: ReprocessingBatch | null; readonly page: ReprocessingPage | null; readonly accepted: ReprocessingAccepted | null }
export function ReprocessingPanel({projectId,availableRevisions,correctionBlocked,announce,onBlocked,onAccepted,port=nativeDocumentReprocessingPort}: Props): ReactNode {
  const [queue,setQueue]=useState<ReprocessingQueue | null>(null), [batch,setBatch]=useState<ReprocessingBatch | null>(null), [page,setPage]=useState<ReprocessingPage | null>(null);
  const [chosen,setChosen]=useState<readonly string[]>([]), [nodes,setNodes]=useState<readonly ReprocessingNode[]>([]), [mappings,setMappings]=useState<readonly ReprocessingMapping[]>([]);
  const [rationale,setRationale]=useState(""), [busy,setBusy]=useState(false), [unknown,setUnknown]=useState<Pending | null>(null), [confirmed,setConfirmed]=useState(false);
  const [impact,setImpact]=useState<ReprocessingAccepted | null>(null), [message,setMessage]=useState("Reprocessing creates proposals. Accepted revisions change only after an explicit decision for each document.");
  const live=useRef(true), owned=useRef(false), serial=useRef(0);
  const dirty=Boolean(mappings.length || rationale), blocked=busy || dirty || Boolean(unknown), disabled=busy || Boolean(unknown) || correctionBlocked;
  useEffect(()=> {onBlocked(blocked);return ()=>onBlocked(false);},[blocked,onBlocked]);
  useEffect(()=> {live.current=true;return ()=> {live.current=false;serial.current+=1;owned.current=false;};},[projectId,port]);
  function notify(value: string): void {setMessage(value);announce(value);}
  async function guarded(run: (current: ()=>boolean)=>Promise<void>): Promise<void> {
    if (owned.current || !live.current || correctionBlocked) return;
    owned.current=true;setBusy(true);const ticket=++serial.current;const current=(): boolean=>live.current && serial.current === ticket;
    try {await run(current);} catch {if (current()) notify("The saved comparison or current authority could not be confirmed. Refresh retained state before deciding.");}
    finally {if (current()) {owned.current=false;setBusy(false);}}
  }
  function show(next: ReprocessingPage, append: boolean): void {
    const same=page?.comparisonRevisionId === next.comparisonRevisionId && page.generation === next.generation && page.planRevisionId === next.planRevisionId;
    setPage(next);setConfirmed(false);
    if (!append || !same) {setNodes(next.candidateNodes);setMappings([]);setRationale("");}
    else setNodes(prior=> {const retained=prior.filter(n=>mappings.some(m=>m.nodeId === n.nodeId || m.relatedNodeId === n.nodeId));return [...retained,...next.candidateNodes.filter(n=>!retained.some(p=>p.nodeId === n.nodeId))];});
  }
  async function compare(selected: ReprocessingBatch, item: ReprocessingItem, offset: number, current: ()=>boolean): Promise<void> {
    const next=decodeReprocessingPage(await port.request(projectId,{action:"compare",batchRevisionId:selected.batchRevisionId,itemId:item.itemId,offset}),projectId,selected.batchRevisionId,item.itemId);
    if (!current()) return;if (!next || next.batchId !== selected.batchId || next.baseRevisionId !== item.baseRevisionId || next.jobId !== item.jobId) throw new Error("reprocessing-comparison-unavailable");
    show(next,offset !== 0);setImpact(null);
    notify(next.state === "base-conflict" ? "The accepted revision has changed. This saved proposal cannot replace it." : "Comparison loaded. Review changed structure, anchor candidates and every retained correction; no revision has been accepted.");
  }
  async function refresh(current: ()=>boolean, afterBatchId: string | null=null): Promise<void> {
    const next=decodeReprocessingQueue(await port.request(projectId,{action:"queue",afterBatchId}),projectId);
    if (!current()) return;if (!next) throw new Error("reprocessing-queue-unavailable");setQueue(next);
    notify(next.items.length ? "Retained reprocessing batches loaded under current project authority." : "No retained reprocessing batches. Select accepted document revisions to create a proposal batch.");
  }
  async function write(pending: Pending, current: ()=>boolean): Promise<void> {
    const command=pending.command;let result: unknown;
    try {result=await port.request(projectId,command);} catch (error) {
      if (current() && String(error).includes("reprocessing-outcome-unknown")) {setUnknown(pending);notify("The issued command outcome is unknown. Retry its exact identity; new writes and navigation are blocked.");return;}throw error;
    }
    if (!current()) return;
    try {
      if (command.action === "accept" || command.action === "resume-impact") {
        const prior=pending.page, selected=pending.batch;
        if (!selected || (command.action === "accept" ? !prior : !pending.accepted)) throw new Error("reprocessing-context-unavailable");
        const accepted=decodeReprocessingAccepted(result,projectId,command.action === "resume-impact" ? command.batchRevisionId : selected.batchRevisionId,command.action === "resume-impact" ? command.itemId : prior!.itemId);
        if (!accepted || accepted.batchId !== selected.batchId || (command.action === "accept" ? accepted.previousRevisionId !== command.acceptance.expectedCurrentRevisionId : accepted.impactRunId !== pending.accepted!.impactRunId || accepted.revisionId !== pending.accepted!.revisionId || accepted.previousRevisionId !== pending.accepted!.previousRevisionId)) throw new Error("reprocessing-acceptance-unconfirmed");
        setImpact(accepted);setMappings([]);setRationale("");setConfirmed(false);if (prior) setPage({...prior,currentRevisionId:accepted.revisionId,state:"base-conflict"});
        // The definitive command outcome is retained before later read-only refreshes.
        setUnknown(null);notify(accepted.impactState === "completed" ? "This document's reparse was explicitly accepted. Only affected downstream records were invalidated; earlier revisions remain retained." : "This document's reparse was accepted. Downstream invalidation is pending; resume it explicitly before relying on dependent results.");
        try {
          if (command.action === "accept" && prior) await onAccepted(prior,accepted);
          if (!current()) return;
          const retained=decodeReprocessingBatch(await port.request(projectId,{action:"read",batchRevisionId:selected.batchRevisionId}),projectId);
          if (!current()) return;if (retained && retained.batchId === selected.batchId) setBatch(retained);
        } catch {if (current()) notify("The reparse acceptance is confirmed and retained. Refresh the Reader or batch to inspect current saved state.");}
        return;
      }
      if (command.action === "reconcile") {
        const prior=pending.page;
        if (!prior) throw new Error("reprocessing-context-unavailable");
        const next=decodeReprocessingPage(result,projectId,prior.batchRevisionId,prior.itemId);
        if (!next || next.comparisonRevisionId !== command.reconciliation.comparisonRevisionId || next.baseRevisionId !== prior.baseRevisionId || next.jobId !== prior.jobId || next.attemptId !== prior.attemptId || next.resultId !== prior.resultId || !next.planRevisionId || next.planRevisionId === command.reconciliation.expectedPlanRevisionId) throw new Error("reprocessing-plan-unconfirmed");
        show(next,false);notify(next.state === "ready-to-accept" ? "Complete reconciliation and current impact saved. Confirm this exact plan to accept this document." : "This correction generation is reconciled. Review and map the next generation before acceptance.");
      } else {
        const next=decodeReprocessingBatch(result,projectId);
        if (!next) throw new Error("reprocessing-batch-unconfirmed");
        if (command.action === "create" && (next.items.length !== command.batch.baseRevisionIds.length || next.items.some((item,index)=>item.baseRevisionId !== command.batch.baseRevisionIds[index]))) throw new Error("reprocessing-batch-substituted");
        if ((command.action === "continue" || command.action === "cancel") && pending.batch && next.batchId !== pending.batch.batchId) throw new Error("reprocessing-batch-substituted");
        if (command.action === "cancel" && next.state !== "cancelled") throw new Error("reprocessing-cancellation-unconfirmed");
        if (command.action === "continue" && !next.items.some(item=>item.itemId === command.continuation.itemId)) throw new Error("reprocessing-continuation-unconfirmed");
        setBatch(next);setPage(null);setNodes([]);setImpact(null);setChosen([]);setConfirmed(false);
        notify(next.state === "cancelled" ? "Future batch work is cancelled. Documents already accepted remain accepted." : "Batch retained. Process pending jobs in Task Center, then refresh and compare each ready item. Acceptance is never automatic.");
      }
      setUnknown(null);
    } catch (error) {
      // A successful transport without an authenticated reply cannot clear an issued write.
      setUnknown(pending);notify("The reply did not confirm the exact issued command. Its identity is retained for reconciliation.");throw error;
    }
  }
  function issue(command: ReprocessingCommand): void {const pending={command,batch,page,accepted:impact};void guarded(current=>write(pending,current));}
  function mapping(obligationId: string, field: "nodeId" | "relatedNodeId", value: string): void {
    const prior=mappings.find(m=>m.obligationId === obligationId) ?? {obligationId,nodeId:"",relatedNodeId:null,referenceId:null};
    const selected=nodes.find(n=>n.nodeId === value), next={...prior,[field]:value || null};
    if (field === "nodeId") {next.nodeId=value;next.referenceId=page?.obligations.find(o=>o.obligationId === obligationId)?.operation === "reference-rematch" ? selected?.referenceId ?? null : null;}
    setMappings([...mappings.filter(m=>m.obligationId !== obligationId),next]);setConfirmed(false);
  }
  function differenceList(items: readonly ReprocessingDifference[], label: string): ReactNode {
    return <section aria-label={label}><h3>{label}</h3>{items.length ? <ol className="quality-node-list">{items.map((d,index)=><li key={`${d.kind}:${d.oldId}:${d.newId}:${index}`}><StatusBadge tone={d.state === "unchanged" ? "success" : "info"}>{d.state}</StatusBadge><p>{d.kind}: prior {d.oldPreview ?? "No retained text"}</p><p>Candidate: {d.newPreview ?? "No candidate reported"}</p><p className="small">{d.oldLocator?.kind === "page-region" ? `Prior original page ${d.oldLocator.pageIndex+1}` : "Prior locator retained in comparison"}; {d.newLocator?.kind === "page-region" ? `candidate original page ${d.newLocator.pageIndex+1}` : "candidate locator retained in comparison"}. Mapping candidates do not move existing anchors.</p></li>)}</ol> : <p>No entries on this comparison page.</p>}</section>;
  }
  function qualityVector(value: ReprocessingAssessment, label: string): ReactNode {
    return <section aria-label={label}><h3>{label}</h3><p>{value.availability}. Review reasons: {value.reviewReasons.join(", ") || "No reasons reported"}. Scholarly claims remain unverified.</p><div className="quality-dimensions">{Object.entries(value.dimensions).map(([name,dimension])=><div key={name}><h4>{name.replace(/([A-Z])/gu," $1")}</h4><dl>{Object.entries(dimension).map(([key,observation])=><div key={key}><dt>{key.replace(/([A-Z])/gu," $1")}</dt><dd>{observation === null ? "Not reported" : typeof observation === "object" ? JSON.stringify(observation) : String(observation)}</dd></div>)}</dl></div>)}</div></section>;
  }
  return <Panel title="Reprocessing impact"><p role="status" aria-live="polite">{message}</p>
    <p>Each document keeps its current accepted structure until you approve its exact comparison and reconciliation plan. Estimated completion time is not reported.</p>
    <fieldset disabled={disabled || dirty}><legend>Accepted revisions to reprocess (up to 10)</legend>{availableRevisions.map(revision=><label key={revision}><input type="checkbox" checked={chosen.includes(revision)} onChange={e=>setChosen(e.currentTarget.checked ? [...chosen,revision].slice(0,10) : chosen.filter(id=>id !== revision))} />Document revision <span className="quality-id">{revision}</span></label>)}</fieldset>
    <div className="ro-action-row"><Button disabled={disabled || dirty || !chosen.length} onClick={()=>issue({action:"create",batch:{schemaVersion:"1.0",commandId:newAttachmentId(),baseRevisionIds:chosen}})}>Reprocess selected</Button><Button disabled={disabled || dirty} onClick={()=>void guarded(current=>refresh(current))}>Load retained reprocessing batches</Button></div>
    {queue ? <><ul>{queue.items.map(b=><li key={b.batchId}><Button disabled={disabled || dirty} onClick={()=>void guarded(async current=> {const saved=decodeReprocessingBatch(await port.request(projectId,{action:"read",batchRevisionId:b.batchRevisionId}),projectId);if (!current()) return;if (!saved || saved.batchId !== b.batchId) throw new Error("reprocessing-batch-unavailable");setBatch(saved);setPage(null);setNodes([]);setImpact(null);})}>Inspect batch {b.batchId}</Button> · {b.state}</li>)}</ul>{queue.nextAfterBatchId ? <Button disabled={disabled || dirty} onClick={()=>void guarded(current=>refresh(current,queue.nextAfterBatchId))}>Next reprocessing batches</Button> : null}</> : null}
    {batch ? <section aria-label="Reprocessing batch"><h3>Batch outcomes</h3><p>{batch.state}. {batch.items.filter(i=>i.state === "accepted").length} of {batch.items.length} documents accepted.</p><ul className="quality-node-list">{batch.items.map(item=><li key={item.itemId}><p>Prior revision <span className="quality-id">{item.baseRevisionId}</span>: {item.state}</p>{item.acceptedRevisionId ? <><p>Accepted revision <span className="quality-id">{item.acceptedRevisionId}</span></p><Button disabled={disabled || dirty} onClick={()=>void guarded(async current=> {const retained=decodeReprocessingAccepted(await port.request(projectId,{action:"read-impact",batchRevisionId:batch.batchRevisionId,itemId:item.itemId}),projectId,null,item.itemId);if (!current()) return;if (!retained || retained.batchId !== batch.batchId || retained.previousRevisionId !== item.baseRevisionId || retained.revisionId !== item.acceptedRevisionId) throw new Error("reprocessing-impact-unavailable");setImpact(retained);setPage(null);setNodes([]);setConfirmed(false);notify("Retained downstream invalidation read under current authority. Resume pending work explicitly; acceptance is not repeated.");})}>Inspect retained downstream invalidation</Button></> : null}<div className="ro-action-row"><Button disabled={disabled || dirty || item.state !== "ready" || batch.state !== "active"} onClick={()=>void guarded(current=>compare(batch,item,0,current))}>Compare this document</Button>{["not-submitted","needs-continuation","failed","processing"].includes(item.state) ? <Button disabled={disabled || dirty || batch.state !== "active"} onClick={()=>issue({action:"continue",continuation:{schemaVersion:"1.0",commandId:newAttachmentId(),batchRevisionId:batch.batchRevisionId,itemId:item.itemId,expectedJobId:item.jobId}})}>Continue this item in current session</Button> : null}</div></li>)}</ul><Button disabled={disabled || dirty} onClick={()=>void guarded(async current=> {const next=decodeReprocessingBatch(await port.request(projectId,{action:"read",batchRevisionId:batch.batchRevisionId}),projectId);if (!current()) return;if (!next || next.batchId !== batch.batchId) throw new Error("reprocessing-batch-unavailable");setBatch(next);notify("Per-document outcomes refreshed. No acceptance was performed.");})}>Refresh batch outcomes</Button><Button disabled={disabled || dirty || batch.state !== "active"} onClick={()=>issue({action:"cancel",cancellation:{schemaVersion:"1.0",commandId:newAttachmentId(),batchRevisionId:batch.batchRevisionId}})}>Cancel future batch work</Button></section> : null}
    {page ? <section aria-label="Reparse comparison"><h3>Old and new comparison</h3><p>Prior accepted revision <span className="quality-id">{page.baseRevisionId}</span>. Complete unresolved corrections: {page.unresolvedCount} of {page.totalObligations}. State: {page.state}.</p><div className="quality-comparison">{differenceList(page.differences,"Structure and reference differences")}{differenceList(page.anchorCandidates,"Anchor migration candidates")}</div><dl>{Object.entries(page.differenceCounts).map(([state,total])=><div key={state}><dt>{state} structure/reference objects</dt><dd>{total}</dd></div>)}{Object.entries(page.anchorCounts).map(([state,total])=><div key={`anchor:${state}`}><dt>{state} anchors</dt><dd>{total}</dd></div>)}</dl><div className="quality-comparison">{qualityVector(page.oldQuality,"Prior quality observations")}{qualityVector(page.newQuality,"Candidate quality observations")}</div>
      {page.nextOffset !== null && batch ? <Button disabled={disabled} onClick={()=> {const item=batch.items.find(i=>i.itemId === page.itemId);if (item) void guarded(current=>compare(batch,item,page.nextOffset!,current));}}>Next comparison page and candidate objects</Button> : null}
      <h3>Manual correction reconciliation</h3><p>Generation {Math.min(page.generation+1,page.generationCount)} of {page.generationCount}. Choose the candidate targets for every operation shown; later generations use the preceding reconciled preview.</p>
      {page.obligations.map(obligation=><fieldset key={obligation.obligationId} disabled={disabled || page.state === "base-conflict"}><legend>{obligation.operation} on {obligation.oldPreview || "retained object"}</legend><p>Original human rationale: {obligation.originalRationale}. Author <span className="quality-id">{obligation.originalAuthor}</span>.</p><label>Candidate target<select value={mappings.find(m=>m.obligationId === obligation.obligationId)?.nodeId ?? ""} onChange={e=>mapping(obligation.obligationId,"nodeId",e.currentTarget.value)}><option value="">Choose a candidate object</option>{nodes.map(n=><option key={n.nodeId} value={n.nodeId}>{n.order+1}: {n.kind} · {n.preview || "No text reported"}</option>)}</select></label>{obligation.relatedOldNodeId ? <label>Related candidate object<select value={mappings.find(m=>m.obligationId === obligation.obligationId)?.relatedNodeId ?? ""} onChange={e=>mapping(obligation.obligationId,"relatedNodeId",e.currentTarget.value)}><option value="">Choose the related object</option>{nodes.map(n=><option key={n.nodeId} value={n.nodeId}>{n.order+1}: {n.kind} · {n.preview || "No text reported"}</option>)}</select></label> : null}</fieldset>)}
      <label>Reconciliation rationale<textarea value={rationale} maxLength={2000} disabled={disabled || page.state === "base-conflict"} onChange={e=> {setRationale(e.currentTarget.value);setConfirmed(false);}} /></label><div className="ro-action-row"><Button disabled={disabled || page.state === "base-conflict" || !rationale.trim() || Array.from(rationale).length > 1000 || mappings.length !== page.obligations.length || mappings.some(m=>!m.nodeId || (page.obligations.find(o=>o.obligationId === m.obligationId)?.relatedOldNodeId && !m.relatedNodeId))} onClick={()=>issue({action:"reconcile",reconciliation:{schemaVersion:"1.0",commandId:newAttachmentId(),comparisonRevisionId:page.comparisonRevisionId,expectedPlanRevisionId:page.planRevisionId,rationale,mappings}})}>Save exact reconciliation and impact</Button><Button disabled={disabled || !dirty} onClick={()=> {setMappings([]);setRationale("");setConfirmed(false);notify("Unsaved reconciliation choices undone. Saved decisions and accepted revisions remain retained.");}}>Undo unsaved reconciliation</Button></div>
      <dl><dt>Affected downstream revisions</dt><dd>{page.impact.affectedCount}</dd><dt>Informational relations</dt><dd>{page.impact.informationalCount}</dd><dt>Legacy relations with unreported impact</dt><dd>{page.impact.legacyUnreportedCount}</dd></dl><p>Impact is prospective and rechecked at acceptance. Existing anchors keep their exact old revision; recomputation is separate.</p><label><input type="checkbox" checked={confirmed} disabled={disabled || dirty || page.state !== "ready-to-accept"} onChange={e=>setConfirmed(e.currentTarget.checked)} />I approve this exact saved reconciliation plan and impact for this document.</label><Button disabled={disabled || dirty || !confirmed || page.state !== "ready-to-accept" || page.unresolvedCount !== 0 || !page.planRevisionId || !page.confirmationSha256} onClick={()=> {if (page.planRevisionId && page.confirmationSha256) issue({action:"accept",acceptance:{schemaVersion:"1.0",commandId:newAttachmentId(),planRevisionId:page.planRevisionId,expectedCurrentRevisionId:page.baseRevisionId,confirmationSha256:page.confirmationSha256,expectedGraphSha256:page.impact.graphSha256,decision:"accept-reparse"}});}}>Approve exact reparse for this document</Button>
    </section> : null}
    {impact && batch ? <section aria-label="Retained downstream invalidation"><h3>Retained downstream invalidation</h3><p>{impact.impactState}: {impact.processedItems} of {impact.totalItems} affected records processed. Recalculation is separate.</p>{impact.impactState === "running" ? <Button disabled={disabled || dirty} onClick={()=>issue({action:"resume-impact",batchRevisionId:impact.batchRevisionId,itemId:impact.itemId,expectedCheckpointSha256:impact.impactCheckpointSha256})}>Resume pending downstream invalidation</Button> : null}</section> : null}
    {unknown ? <section aria-label="Reconcile pending reprocessing command"><h3>Reconcile pending reprocessing command</h3><p>The exact issued payload is retained in this session. Reading saved state alone does not determine its outcome.</p><Button disabled={busy || correctionBlocked} onClick={()=>void guarded(current=>write(unknown,current))}>Retry exact pending reprocessing command</Button></section> : null}
  </Panel>;
}
