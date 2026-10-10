// Actual production controls/Native IPC in a declared owned Wry test host.
// Parser selection/result delivery is an authored fixture, not a model claim.
import { invoke } from "@tauri-apps/api/core";
import type { ProjectProjection } from "@research-observatory/contracts/core-api";
import type { QualitySelection } from "../../../apps/desktop/src/app/ParsingQualityWorkspace";
export async function runReprocessingNativeDriver(project: ProjectProjection,selection: QualitySelection): Promise<void> {
  let phase="mount";
  const api=(window as unknown as {__QUALITY_NATIVE_WITNESS__:{mountNative:(project:ProjectProjection,selection:QualitySelection)=>void}}).__QUALITY_NATIVE_WITNESS__;
  const wait=async(predicate:()=>boolean):Promise<void>=> {const deadline=performance.now()+30000;while(!predicate()) {if (performance.now() > deadline) throw new Error("witness-timeout");await new Promise(resolve=>setTimeout(resolve,25));}};
  const button=(name:string):HTMLButtonElement | undefined=>Array.from(document.querySelectorAll("button")).find(b=>b.textContent?.trim() === name && !b.disabled);
  const click=async(name:string):Promise<void>=> {await wait(()=>Boolean(button(name)));button(name)!.click();};
  const labelled=(prefix:string):HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement=> {
    const control=Array.from(document.querySelectorAll("label")).find(l=>l.textContent?.startsWith(prefix))?.querySelector("input,textarea,select");
    if (!(control instanceof HTMLInputElement || control instanceof HTMLTextAreaElement || control instanceof HTMLSelectElement)) throw new Error("witness-control-unavailable");return control;
  };
  const fill=(name:string,value:string):void=> {const control=labelled(name);const prototype=control instanceof HTMLInputElement ? HTMLInputElement.prototype : control instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLTextAreaElement.prototype;Object.getOwnPropertyDescriptor(prototype,"value")!.set!.call(control,value);control.dispatchEvent(new Event(control instanceof HTMLSelectElement ? "change" : "input",{bubbles:true}));};
  try {
    api.mountNative(project,selection);await click("Correct object 1");phase="correction";
    fill("Human section label","SYNTHETIC Native retained reparse label");await click("Add proposed correction");fill("Correction rationale","SYNTHETIC original Native human rationale");await click("Save proposal and preview");
    await wait(()=>document.body.innerText.includes("Proposal saved and previewed."));await click("Preview current impact");
    await wait(()=>Boolean(Array.from(document.querySelectorAll("label")).find(l=>l.textContent?.startsWith("I accept this exact saved proposal"))));labelled("I accept this exact saved proposal").click();await click("Accept exact saved correction");
    await wait(()=>document.body.innerText.includes("Correction explicitly accepted."));phase="batch";
    labelled("Document revision ").click();await click("Reprocess selected");
    const deadline=performance.now()+30000;
    while (!button("Compare this document")) {
      if (performance.now() > deadline) throw new Error("witness-parse-not-ready");
      await click("Refresh batch outcomes");
      await new Promise(resolve=>setTimeout(resolve,100));
      // Let the actual Native/Core read settle before inspecting the ready
      // Compare control. Re-clicking refresh while it was busy hid readiness.
      await wait(()=>Boolean(button("Refresh batch outcomes")));
    }
    await click("Compare this document");phase="reconciliation";
    await wait(()=>Boolean(Array.from(document.querySelectorAll("label")).find(l=>l.textContent?.startsWith("Candidate target"))));
    const target=labelled("Candidate target");if (!(target instanceof HTMLSelectElement) || target.options.length < 2) throw new Error("witness-target-unavailable");fill("Candidate target",target.options[1]!.value);
    fill("Reconciliation rationale","SYNTHETIC explicitly carry retained human correction into reparse");await click("Save exact reconciliation and impact");
    await wait(()=>document.body.innerText.includes("Complete reconciliation and current impact saved."));phase="acceptance";
    labelled("I approve this exact saved reconciliation plan").click();await click("Approve exact reparse for this document");
    await wait(()=>document.body.innerText.includes("This document's reparse was explicitly accepted."));
    await click("Open accepted revision in Reader");phase="reader";await click("Inspect accepted human corrections");
    await wait(()=>document.body.innerText.includes("Human label: SYNTHETIC Native retained reparse label"));await click("Return to Parsing Quality");phase="return";
    await wait(()=>Boolean(document.querySelector('[aria-label="Accepted structure"]')?.textContent?.includes("SYNTHETIC Native retained reparse label")));
    await invoke("reprocessing_witness_complete",{report:{schemaVersion:"1.0",passed:true,phase:"complete"}});
  } catch {
    const text=document.body.innerText;
    const diagnostic=text.includes("issued command outcome is unknown") || text.includes("reply did not confirm the exact issued command") ? "unknown-command" : text.includes("current authority could not be confirmed") ? "unconfirmed-authority" : document.querySelector('[aria-label="Reprocessing batch"]')?.textContent?.includes(": processing") ? "parse-pending" : "control-timeout";
    const observedStatus=Array.from(document.querySelectorAll('[role="status"]')).map(s=>s.textContent ?? "").slice(0,5).join(" | ").slice(0,1000);
    await invoke("reprocessing_witness_complete",{report:{schemaVersion:"1.0",passed:false,phase,diagnostic,observedStatus}});
  }
}
