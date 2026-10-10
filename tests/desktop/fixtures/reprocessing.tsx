// Actual production components with explicitly authored test ports.
import React from "react";
import { createRoot } from "react-dom/client";
import type { ProjectProjection } from "@research-observatory/contracts/core-api";
import { ParsingQualityWorkspace } from "../../../apps/desktop/src/app/ParsingQualityWorkspace";
import { correctionSource } from "./document-correction";
import {state,correction,reprocessing} from "./reprocessing-ports";
import "../../../packages/ui-tokens/index.css";
import "../../../packages/ui-components/src/styles.css";
import "../../../apps/desktop/src/app.css";
const root=createRoot(document.getElementById("root")!);
const project={projectId:correctionSource.projectId,root:"SYNTHETIC test root",open:true,compatibilityState:"compatible"} as ProjectProjection;
function mount(active=true): void {root.render(<ParsingQualityWorkspace project={project} active={active} port={correction} reprocessingPort={reprocessing} announce={()=>{}} onNavigationBlocked={value=> {state.blocked=value;}} onReader={(_source,_revision,selection)=> {state.returns.push(selection);mount(false);}} />);}
Object.assign(window,{__REPROCESSING_MOUNT__:mount});mount();
