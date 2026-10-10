// Test host for the unchanged production workspace. Mock mode proves UI only;
// Native mode uses its actual production IPC port in an owned Wry window.
import React from "react";
import {createRoot} from "react-dom/client";
import type {ProjectProjection} from "@research-observatory/contracts/core-api";
import {ParsingQualityWorkspace, type QualitySelection} from "../../../apps/desktop/src/app/ParsingQualityWorkspace";
import {DocumentViewerWorkspace} from "../../../apps/desktop/src/app/DocumentViewerWorkspace";
import {decodeCorrectionPage,decodeCorrectionDraft,nativeDocumentCorrectionPort,type CorrectionPage,type CorrectionDraftView,type CorrectionCommand,type DocumentCorrectionPort} from "../../../apps/desktop/src/app/documentCorrections";
import {correctionPageFixture,correctionDraftFixture,correctionQualityFixture,correctionSource,correctionIdentity,correctionRevision} from "./document-correction";
import {runQualityNativeDriver} from "./parsing-quality-native-driver";
import {runReprocessingNativeDriver} from "./reprocessing-native-driver";
import "../../../packages/ui-tokens/index.css";
import "../../../packages/ui-components/src/styles.css";
import "../../../apps/desktop/src/app.css";
const root=createRoot(document.getElementById("root")!);
const original=decodeCorrectionPage(correctionPageFixture(),correctionSource.projectId,correctionRevision)!;
const state={page:original,history:new Map<string,CorrectionPage>([[original.revisionId,original]]),calls:[] as CorrectionCommand[],serial:0,hold:false,release:null as (()=>void) | null,deny:false,unknown:false,blocked:false,returns:[] as QualitySelection[],native:false};
const mock: DocumentCorrectionPort={async request(project,command) {
  state.calls.push(command); if(state.hold) await new Promise<void>(resolve=> {state.release=resolve;}); if(state.deny) return null;
  if(command.action === "queue") return {schemaVersion:"1.0",projectId:project,items:[{jobId:original.jobId,attachmentId:original.attachmentId,revisionId:state.page.revisionId}],nextAfterJobId:null};
  if(command.action === "quality") return correctionQualityFixture();
  if(command.action === "page") return state.history.get(command.revisionId) ?? null;
  if(command.action === "save") {
    if(state.unknown) throw new Error("correction-outcome-unknown");
    const c=command.correction, f=correctionDraftFixture();
    const record={...f.record,commandId:c.commandId,draftId:c.draftId ?? correctionIdentity(2000 + ++state.serial),revisionId:correctionIdentity(3000 + ++state.serial),previousDraftRevisionId:c.expectedDraftRevisionId,patch:c.patch,rationale:c.rationale};
    const d=decodeCorrectionDraft({record,confirmationSha256:f.confirmationSha256},project)!;
    state.page={...state.page,draft:d,drafts:[{draftRevisionId:d.record.revisionId,baseRevisionId:state.page.revisionId}],previewNodes:state.page.nodes.map(n=>({...n,state:"proposed",expectedNodeSha256:null,label:c.patch.operations.find(op=>op.nodeId === n.nodeId && op.op === "relabel")?.op === "relabel" ? (c.patch.operations.find(op=>op.nodeId === n.nodeId && op.op === "relabel") as {label:string}).label : n.label}))};
    state.history.set(state.page.revisionId,state.page);return d;
  }
  if(command.action === "impact") return {schemaVersion:"1.0",projectId:project,baseRevisionId:state.page.revisionId,draftRevisionId:command.draftRevisionId,graphSha256:"a".repeat(64),affectedCount:0,informationalCount:0,legacyUnreportedCount:0,items:[],truncated:false,state:"prospective-rechecked-at-acceptance"};
  if(command.action === "accept") {
    if(state.unknown) throw new Error("correction-outcome-unknown");
    const prior=state.page, revision=correctionIdentity(4000 + ++state.serial), node=correctionIdentity(5000 + state.serial), label=prior.previewNodes[0]?.label ?? null;
    state.page={...prior,revisionId:revision,currentRevisionId:revision,structureSha256:"3".repeat(64),nodes:prior.nodes.map(n=>({...n,nodeId:node,label,expectedNodeSha256:"4".repeat(64)})),previewNodes:[],draft:null,acceptedDecision:prior.draft,acceptedLabels:label ? [{nodeId:node,label}] : []};
    state.history.set(revision,state.page);
    return {schemaVersion:"1.0",projectId:project,documentId:prior.documentId,revisionId:revision,previousRevisionId:prior.revisionId,structureSha256:state.page.structureSha256,contentSha256:"5".repeat(64),decisionRevisionId:correctionIdentity(6000 + state.serial),acceptedBy:prior.acceptedBy,acceptedAt:prior.acceptedAt,scholarlyVerification:"unverified"};
  }
  if(command.action === "discard") {const prior=state.page.draft!;const d={...prior,record:{...prior.record,revisionId:correctionIdentity(7000+ ++state.serial),previousDraftRevisionId:prior.record.revisionId,state:"discarded",commandKind:"discard",commandId:command.discard.commandId,rationale:command.discard.rationale}} as CorrectionDraftView;state.page={...state.page,draft:d,previewNodes:[]};state.history.set(state.page.revisionId,state.page);return d;}
  if(command.action === "targets") return {schemaVersion:"1.0",projectId:project,items:[],nextAfterWorkId:null};
  return state.page.draft;
}};
const project={projectId:original.projectId,root:"SYNTHETIC test root",open:true,compatibilityState:"compatible"} as ProjectProjection;
let nativeProject: ProjectProjection | null=null, savedSelection: QualitySelection | null=null;
function mount(active=true): void {
  const p=nativeProject ?? project;
  root.render(<ParsingQualityWorkspace project={p} active={active} port={state.native ? nativeDocumentCorrectionPort : mock} selection={savedSelection} announce={()=>{}} onNavigationBlocked={blocked=> {state.blocked=blocked;}}
    onReader={(source,revision,selection)=> {
      state.returns.push(selection);savedSelection=selection;
      if(!state.native) {mount(false);return;}
      root.render(<DocumentViewerWorkspace project={p} active={true} initialRevision={revision} handoff={{attachmentId:source.attachmentId,documentRevisionId:source.documentRevisionId,operationId:null,commitRequest:null,selection:{projectId:source.projectId,workId:source.workId,workRevisionId:source.workRevisionId,versionId:source.versionId,versionRevisionId:source.versionRevisionId,sourceAssertionRevisionId:source.sourceAssertionRevisionId}}}
        returnLabel="Return to Parsing Quality" announce={()=>{}} onReturn={()=>mount()} />);
    }} />);
}
Object.assign(window,{__QUALITY_UI_TEST__:state,__REPROCESSING_NATIVE_DRIVER__:runReprocessingNativeDriver,__QUALITY_NATIVE_WITNESS__:{mount,run:runQualityNativeDriver,mountNative:(p:ProjectProjection,selection:QualitySelection)=> {state.native=true;nativeProject=p;savedSelection=selection;mount();}}});
if(!("__TAURI_INTERNALS__" in window)) mount();
