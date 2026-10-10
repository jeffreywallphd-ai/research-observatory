// Exact owned synthetic UI journey using production controls and Native IPC.
import {invoke} from "@tauri-apps/api/core";
import type {ProjectProjection} from "@research-observatory/contracts/core-api";
import type {QualitySelection} from "../../../apps/desktop/src/app/ParsingQualityWorkspace";

export async function runQualityNativeDriver(project: ProjectProjection,selection: QualitySelection): Promise<void> {
  let phase="mount";
  const api=(window as unknown as {__QUALITY_NATIVE_WITNESS__:{mountNative:(p:ProjectProjection,s:QualitySelection)=>void}}).__QUALITY_NATIVE_WITNESS__;
  const wait=async (predicate:()=>boolean): Promise<void>=> {const deadline=performance.now()+20000;while(!predicate()) {if(performance.now()>deadline) throw new Error("witness-timeout");await new Promise(resolve=>setTimeout(resolve,25));}};
  const button=(name:string): HTMLButtonElement | undefined=>Array.from(document.querySelectorAll("button")).find(b=>b.textContent?.trim() === name && !b.disabled);
  const click=async(name:string):Promise<void>=> {await wait(()=>Boolean(button(name)));button(name)!.click();};
  const fill=(label:string,value:string):void=> {
    const control=Array.from(document.querySelectorAll("label")).find(l=>l.textContent?.startsWith(label))?.querySelector("input,textarea");
    if(!(control instanceof HTMLInputElement || control instanceof HTMLTextAreaElement)) throw new Error("witness-control-unavailable");
    Object.getOwnPropertyDescriptor(control instanceof HTMLInputElement ? HTMLInputElement.prototype : HTMLTextAreaElement.prototype,"value")!.set!.call(control,value);
    control.dispatchEvent(new Event("input",{bubbles:true}));
  };
  try {
    api.mountNative(project,selection);
    await click("Correct object 1");phase="proposal";
    fill("Human section label","SYNTHETIC Native human label");
    await click("Add proposed correction");fill("Correction rationale","SYNTHETIC Native human rationale");
    await click("Save proposal and preview");
    await wait(()=>document.body.innerText.includes("Proposal saved and previewed."));
    const accepted=document.querySelector('[aria-label="Accepted structure"]'),proposed=document.querySelector('[aria-label="Proposed structure"]');
    if(accepted?.textContent?.includes("SYNTHETIC Native human label") || !proposed?.textContent?.includes("SYNTHETIC Native human label")) throw new Error("witness-proposal-separation");
    await click("Preview current impact");phase="acceptance";
    await wait(()=>Boolean(Array.from(document.querySelectorAll("label")).find(l=>l.textContent?.startsWith("I accept this exact saved proposal"))));
    (Array.from(document.querySelectorAll("label")).find(l=>l.textContent?.startsWith("I accept this exact saved proposal"))!.querySelector('input[type="checkbox"]') as HTMLInputElement).click();
    await click("Accept exact saved correction");
    await wait(()=>document.body.innerText.includes("Correction explicitly accepted."));
    await click("Open accepted revision in Reader");phase="reader";
    await click("Inspect accepted human corrections");
    await wait(()=>document.body.innerText.includes("Human label: SYNTHETIC Native human label"));
    await click("Return to Parsing Quality");phase="return";
    await wait(()=>Boolean(document.querySelector('[aria-label="Accepted structure"]')?.textContent?.includes("SYNTHETIC Native human label")));
    await invoke("correction_witness_complete",{report:{schemaVersion:"1.0",passed:true,phase:"complete"}});
  } catch {await invoke("correction_witness_complete",{report:{schemaVersion:"1.0",passed:false,phase}});}
}
