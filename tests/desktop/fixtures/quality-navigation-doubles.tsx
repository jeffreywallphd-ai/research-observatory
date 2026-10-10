import React, {useEffect, useState} from "react";
export {CoreApiClientError} from "../../../packages/contracts/core-api/generated";
const id=(n:number)=>`00000000-0000-7000-8000-${n.toString(16).padStart(12,"0")}`;
const hash=`sha256:${"a".repeat(64)}`;
const project={projectId:id(1),root:"SYNTHETIC navigation fixture",open:true,compatibilityState:"compatible"};
const stage={stageKey:"intent-contract-1",order:1,pageContractId:"intent-contract.html",label:"Synthetic current stage",optional:false,rationale:"Authored navigation fixture",checkpointState:"unknown",checkpointRationale:"No checkpoint grant"};
const profile={profileId:"systematic-review",epistemicMode:"systematic",title:"Synthetic workflow",purpose:"Navigation fixture",example:"Synthetic",expectedOutputs:["Authored output"],processForm:"linear",defaultEvidenceTypes:["theoretical-work"],defaultNoveltyStandard:"not-claimed",defaultAutonomyLevel:"suggest",defaultStoppingConditions:["researcher-decision"],warning:"Synthetic",stages:[stage]};
const catalog={schemaVersion:"1.0",referenceId:"RO-UI-ACADEMIC-MINIMAL-1.5",referenceVersion:"1.5",profileCatalogVersion:"1.0.0",profileCatalogHash:hash,intentGuidanceVersion:"1.0.0",intentGuidanceHash:hash,allToolsAccessible:true,evidenceRequirementsUnchanged:true,provenanceRequirementsUnchanged:true,registeredToolPageContractIds:["intent-contract.html","parsing-quality.html"],profiles:[profile]};
const current={attentionReason:null,completionEvidenceIds:[],navigationRole:"primary",pageContractId:stage.pageContractId,parentStateRevisionId:null,passNumber:1,revision:1,revisionContentHash:hash,skipRationale:null,stageKey:stage.stageKey,stageStateId:id(10),stageStateRevisionId:id(11),staleCauseIds:[],status:"current",updatedAt:"2026-10-10T00:00:00Z"};
const progress={schemaVersion:"1.0",projectId:project.projectId,intentRevisionId:id(2),intentRevisionContentHash:hash,selectionRevisionId:id(3),selectionRevisionContentHash:hash,profileId:profile.profileId,profileTitle:profile.title,processForm:"linear",bootstrapRequired:false,current,recommendedStageKey:stage.stageKey,recommendedPageContractId:stage.pageContractId,recommendedAction:"Inspect",checkpointState:"unknown",checkpointRationale:"Synthetic",staleOutputs:[],history:[],supportingHandoff:{navigationRole:"supporting",pageContractId:"parsing-quality.html",returnStageStateRevisionId:current.stageStateRevisionId,revisionContentHash:hash,stageStateId:id(12),stageStateRevisionId:id(13)}};
export function createCoreApiClient() {return {
  workflowProfileCatalog:async()=>catalog,
  intent:async()=>({projectId:project.projectId,current:{revisionId:id(2),revisionContentHash:hash,primaryUseCase:profile.profileId}}),
  workflowProgress:async()=>progress,commandWorkflowProgress:async()=>progress,
};}
export const packagedProjectTransport=async()=>{throw new Error("Fixture transport is never used");};
export function ProjectsWorkspace({onProjectChange}:{onProjectChange:(p:typeof project)=>void}) {
  return <button onClick={()=>onProjectChange(project)}>Open synthetic fixture project</button>;
}
const state={mode:"clean",command:{commandId:id(20)},unmounted:0};
Object.assign(window,{__QUALITY_NAVIGATION_TEST__:state});
export function ParsingQualityWorkspace({onNavigationBlocked}:{onNavigationBlocked:(blocked:boolean)=>void}) {
  const [mode,setMode]=useState("clean");
  useEffect(()=>()=>{state.unmounted++;},[]);
  return <section aria-label="Synthetic correction ownership">
    <p data-owned-command>{state.command.commandId}</p><p>{mode}</p>
    {["dirty","busy","unknown","clean"].map(next=><button key={next} onClick={()=>{state.mode=next;setMode(next);onNavigationBlocked(next!=="clean");}}>Set correction {next}</button>)}
  </section>;
}
