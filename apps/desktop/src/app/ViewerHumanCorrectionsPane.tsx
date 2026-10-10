import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button, Panel } from "@research-observatory/ui-components";
import type { SourceIdentity } from "./sourceAnchors";
import { viewerSourcesMatch, type ViewerMainAdmission } from "./documentViewer";
import { decodeCorrectionPage, nativeDocumentCorrectionPort, type CorrectionPage, type DocumentCorrectionPort } from "./documentCorrections";

/** Read accepted human relationships beside the unchanged machine assertions. */
export function ViewerHumanCorrectionsPane({ source, revision, announce, main, reserveCore, onFailure, port = nativeDocumentCorrectionPort }: {
  readonly source: SourceIdentity; readonly revision: string; readonly announce: (text: string)=>void; readonly port?: DocumentCorrectionPort;
  readonly main: ViewerMainAdmission; readonly reserveCore: ()=>()=>void; readonly onFailure: (code: string)=>void;
}): ReactNode {
  const [value,setValue]=useState<CorrectionPage | null>(null),[busy,setBusy]=useState(false),[status,setStatus]=useState("Load accepted human corrections to inspect labels and reference selections.");
  const live=useRef(true),owner=useRef(false),generation=useRef(0);
  const retained=useRef<(()=>void) | null>(null);
  useEffect(()=> {live.current=true;setValue(null);setStatus("Load accepted human corrections to inspect labels and reference selections.");return ()=> {live.current=false;generation.current+=1;retained.current?.();retained.current=null;};},[source,revision]);
  async function load(offset: number): Promise<void> {
    if (owner.current || !live.current) return;owner.current=true;setBusy(true);const ticket=++generation.current;
    const current=(): boolean=>live.current && ticket === generation.current;
    retained.current?.();retained.current=null;setValue(null);
    let releaseMain=()=>{},releaseCore=()=>{},terminal=true;
    try {
      releaseMain=main.context();releaseCore=reserveCore();terminal=false;
      const page=decodeCorrectionPage(await port.request(source.projectId,{action:"page",revisionId:revision,draftRevisionId:null,offset}),source.projectId,revision);
      terminal=true;
      if (!current()) return;
      if (!page || !viewerSourcesMatch(source,page.source)) {setValue(null);setStatus("Accepted human corrections could not be confirmed under current source permission.");return;}
      retained.current=releaseMain;setValue(page);setStatus(page.acceptedDecision ? "Accepted human corrections loaded. Machine assertions and scholarly verification remain separate." : "This revision has no accepted human correction decision.");
      announce("Accepted human correction metadata loaded.");
    } catch (error) {terminal=terminal || String(error).includes("correction-unavailable") || String(error).includes("viewer-resource-limit");if(current()) {setValue(null);setStatus("Accepted human corrections are unavailable. Review the current source and permission before retrying.");if(!terminal) onFailure("viewer-owned-read-drain-pending");}}
    finally {if(terminal) {releaseCore();if(retained.current !== releaseMain) releaseMain();}if(current()) {owner.current=false;setBusy(false);}}
  }
  return <Panel title="Accepted human corrections"><p role="status">{status}</p><Button disabled={busy} onClick={()=>void load(0)}>Inspect accepted human corrections</Button>
    {value?.acceptedDecision ? <><p>Accepted by {value.acceptedBy} at {value.acceptedAt}. Rationale: {value.acceptedDecision.record.rationale}</p><ul>{value.acceptedLabels.map(l=><li key={l.nodeId}>Human label: {l.label} · object {value.nodes.find(n=>n.nodeId === l.nodeId)?.order! + 1}</li>)}{value.acceptedReferenceMatches.map(m=><li key={m.referenceId}>Human-selected reference {m.referenceId} points to Work {m.workId}, revision {m.workRevisionId}. This selection is not an exact identifier assertion or scholarly verification.</li>)}</ul>
      {value.nextOffset !== null ? <Button disabled={busy} onClick={()=>void load(value.nextOffset!)}>Next accepted correction relationships</Button> : null}</> : null}
  </Panel>;
}
