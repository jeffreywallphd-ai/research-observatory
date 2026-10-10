// Owned test host mounts the actual Parsing Quality/Reprocessing components.
// Authored ports prove interaction only; Native/Core proof uses a separate mode.
import type { QualitySelection } from "../../../apps/desktop/src/app/ParsingQualityWorkspace";
import { decodeCorrectionPage, type CorrectionPage, type DocumentCorrectionPort } from "../../../apps/desktop/src/app/documentCorrections";
import { decodeReprocessingAccepted, decodeReprocessingBatch, decodeReprocessingPage, type DocumentReprocessingPort, type ReprocessingCommand, type ReprocessingAccepted } from "../../../apps/desktop/src/app/documentReprocessing";
import { correctionPageFixture,correctionQualityFixture,correctionSource,correctionRevision,correctionIdentity } from "./document-correction";
import { reprocessingBatchFixture,reprocessingPageFixture,reprocessingAcceptedFixture,reprocessingBatchRevision,reprocessingItemId } from "./document-reprocessing";
export const state={calls:[] as ReprocessingCommand[],acceptedCount:0,resumedCount:0,createdCount:0,expectedJobId:correctionIdentity(8003),referenceCandidate:false,qualityRegression:false,largeCandidatePages:false,runningImpact:false,blocked:false,hold:false,release:null as (()=>void) | null,unknown:false,invalid:false,returns:[] as QualitySelection[],page:decodeCorrectionPage(correctionPageFixture(),correctionSource.projectId,correctionRevision)!};
let batch=decodeReprocessingBatch(reprocessingBatchFixture(),correctionSource.projectId)!;
let comparison=decodeReprocessingPage(reprocessingPageFixture(),correctionSource.projectId,reprocessingBatchRevision,reprocessingItemId)!;
let acceptedResult: ReprocessingAccepted | null=null;
const replies=new Map<string,unknown>();
export const correction: DocumentCorrectionPort={async request(project,command) {
  if (command.action === "queue") return {schemaVersion:"1.0",projectId:project,items:[{jobId:state.page.jobId,attachmentId:state.page.attachmentId,revisionId:state.page.revisionId}],nextAfterJobId:null};
  if (command.action === "quality") return {...correctionQualityFixture(),jobId:command.jobId};
  if (command.action === "page") return command.revisionId === state.page.revisionId ? state.page : null;
  return null;
}};
export const reprocessing: DocumentReprocessingPort={async request(project,command) {
  state.calls.push(structuredClone(command));if (state.hold) await new Promise<void>(resolve=> {state.release=resolve;});
  const commandId=command.action === "create" ? command.batch.commandId : command.action === "reconcile" ? command.reconciliation.commandId : command.action === "accept" ? command.acceptance.commandId : command.action === "continue" ? command.continuation.commandId : command.action === "cancel" ? command.cancellation.commandId : command.action === "resume-impact" ? `checkpoint:${command.expectedCheckpointSha256}` : null;
  let value: unknown=commandId ? replies.get(commandId) : undefined;
  if (value === undefined) {
    if (command.action === "queue") value={schemaVersion:"1.0",projectId:project,items:[batch],nextAfterBatchId:null};
    else if (command.action === "read") value=batch;
    else if (command.action === "read-impact") value=acceptedResult;
    else if (command.action === "compare") {
      value=state.referenceCandidate ? {...comparison,candidateNodes:comparison.candidateNodes.map(node=>({...node,referenceId:correctionIdentity(9999)}))} : comparison;
      if (state.qualityRegression) value={...comparison,oldQuality:{...comparison.oldQuality,dimensions:{...comparison.oldQuality.dimensions,textCoverage:{state:"reported",basis:"retained-parser-observation",observedCount:8,expectedCount:8,missingCount:0,ratio:1}}},newQuality:{...comparison.newQuality,dimensions:{...comparison.newQuality.dimensions,textCoverage:{state:"reported",basis:"retained-parser-observation",observedCount:3,expectedCount:8,missingCount:5,ratio:0.375}}}};
      if (state.largeCandidatePages) value={...comparison,obligations:Array.from({length:32},(_,index)=>({...comparison.obligations[0]!,obligationId:index.toString(16).padStart(64,"0"),operationIndex:index})),totalObligations:32,unresolvedCount:32,candidateNodes:Array.from({length:20},(_,index)=>({...comparison.candidateNodes[0]!,nodeId:correctionIdentity(20000+command.offset+index),order:command.offset+index,preview:`SYNTHETIC candidate ${command.offset+index}`})),nextOffset:command.offset < 160 ? command.offset+20 : null};
    }
    else if (command.action === "create") {
      const serial=++state.createdCount;
      const batchId=correctionIdentity(10000+serial*10), revision=correctionIdentity(10001+serial*10), itemId=correctionIdentity(10002+serial*10), jobId=correctionIdentity(10003+serial*10);
      state.expectedJobId=jobId;
      batch={...batch,batchId,batchRevisionId:revision,state:"active",items:[{itemId,jobId,baseRevisionId:command.batch.baseRevisionIds[0]!,state:"ready",acceptedRevisionId:null}]};
      comparison=decodeReprocessingPage({...reprocessingPageFixture(),batchId,batchRevisionId:revision,itemId,jobId},project,revision,itemId)!;value=batch;
    }
    else if (command.action === "reconcile") {comparison={...comparison,planRevisionId:correctionIdentity(9000),confirmationSha256:"f".repeat(64),generation:1,unresolvedCount:0,obligations:[],state:"ready-to-accept"};value=comparison;}
    else if (command.action === "accept") {
      const accepted=decodeReprocessingAccepted({...reprocessingAcceptedFixture(),batchId:batch.batchId,batchRevisionId:batch.batchRevisionId,itemId:comparison.itemId,...(state.runningImpact ? {impactState:"running",processedItems:0,totalItems:64} : {})},project,batch.batchRevisionId,comparison.itemId)!;acceptedResult=accepted;
      state.acceptedCount+=1;batch={...batch,items:batch.items.map(item=>({...item,state:"accepted",acceptedRevisionId:accepted.revisionId}))};
      state.page={...state.page,revisionId:accepted.revisionId,currentRevisionId:accepted.revisionId,jobId:comparison.jobId,nodes:state.page.nodes.map(node=>({...node,nodeId:correctionIdentity(9010),label:"SYNTHETIC retained human label"}))};value=accepted;
    } else if (command.action === "cancel") {batch={...batch,batchRevisionId:correctionIdentity(9001),state:"cancelled"};value=batch;}
    else if (command.action === "continue") {batch={...batch,batchRevisionId:correctionIdentity(9002)};value=batch;}
    else if (command.action === "resume-impact" && acceptedResult) {state.resumedCount+=1;acceptedResult={...acceptedResult,impactState:"completed",processedItems:acceptedResult.totalItems,impactCheckpointSha256:"1".repeat(64)};value=acceptedResult;}
    else value=reprocessingAcceptedFixture();
    if (commandId) replies.set(commandId,value);
  }
  // Simulate a committed command whose delivery is lost, preserving its receipt.
  if (commandId && state.unknown) throw new Error("reprocessing-outcome-unknown");
  if (commandId && state.invalid) return null;
  return value;
}};

export function savedReprocessingFixture() { return {batch,comparison}; }
Object.assign(window,{__REPROCESSING_UI_TEST__:state,__REPROCESSING_SAVED__:savedReprocessingFixture});
