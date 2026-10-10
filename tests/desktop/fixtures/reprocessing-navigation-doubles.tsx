// Authored project/transport only; actual Quality and Reprocessing own state.
import React, {useEffect} from "react";
import {ParsingQualityWorkspace as ActualQuality} from "../../../apps/desktop/src/app/ParsingQualityWorkspace";
import {state,correction,reprocessing} from "./reprocessing-ports";
export {createCoreApiClient,packagedProjectTransport,ProjectsWorkspace} from "./quality-navigation-doubles";
let unmounted=0;
Object.assign(window,{__REPROCESSING_ROOT_TEST__:{get unmounted(){return unmounted;}}});
export function ParsingQualityWorkspace(props: Parameters<typeof ActualQuality>[0]) {
  useEffect(()=>()=>{unmounted++;},[]);
  return <ActualQuality {...props} port={correction} reprocessingPort={reprocessing}
    onNavigationBlocked={blocked=>{state.blocked=blocked;props.onNavigationBlocked?.(blocked);}} />;
}
