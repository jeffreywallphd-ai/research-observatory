"""Observe actual enabled current-navigation text; never approve the task.

Independent follow-up to visual-03-F01. Reuse the producer's unchanged settings
workflow, keyboard helper, geometry validators and guarded capture publisher.
The producer and output are explicit; previous observers/bundles are untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


OBSERVER = "artifacts/evidence/W1.A08.T02.context-observer-02.py"
CHECKOUT = ".local/qualification-worktrees/w1-a08-t02"
STATES = ("step", "page")

SETTLE = r"""async () => {
  let previous = '', stable = 0;
  for (let frame = 0; frame < 120; frame++) {
    await new Promise(requestAnimationFrame);
    const selector = '.sidebar button[aria-current], .sidebar button[aria-current] *';
    const colors = JSON.stringify([...document.querySelectorAll(selector)].map(node => {
      const s = getComputedStyle(node), r = node.getBoundingClientRect();
      return [s.color,s.backgroundColor,s.opacity,s.visibility,r.top,r.left,r.width,r.height];
    }));
    const animations = document.getAnimations();
    const running = animations.filter(animation => animation.playState === 'running').length;
    const pending = animations.filter(animation => animation.pending).length;
    stable = !running && !pending && colors === previous ? stable + 1 : 0;
    if (stable >= 3) return {frames:frame+1,stableFrames:stable,runningAnimations:running,pendingAnimations:pending};
    previous = colors;
  }
  throw new Error('current navigation colors/geometry did not settle');
}"""

SAMPLE = r"""button => {
  const rect = element => { const r = element.getBoundingClientRect();
    return {top:r.top,bottom:r.bottom,left:r.left,right:r.right,width:r.width,height:r.height}; };
  const visible = element => {const s=getComputedStyle(element); return Boolean(element.getClientRects().length)
    && s.visibility === 'visible' && s.display !== 'none';};
  const within = r => r.top >= -.5 && r.bottom <= innerHeight+.5 && r.left >= -.5 && r.right <= innerWidth+.5;
  const opacity = element => {const chain=[]; let effective=1;
    for(let node=element; node; node=node.parentElement){const value=Number(getComputedStyle(node).opacity);
      chain.push({tag:node.tagName,value});effective*=value;} return {chain,effective};};
  const nodes = [button,...button.querySelectorAll('*')].flatMap(node => {
    const texts=[...node.childNodes].filter(child=>child.nodeType===Node.TEXT_NODE && child.textContent.trim());
    if(!texts.length) return [];
    let surface=node;
    while(surface && getComputedStyle(surface).backgroundColor === 'rgba(0, 0, 0, 0)') surface=surface.parentElement;
    const ranges=texts.flatMap(child=>{const range=document.createRange();range.selectNode(child);
      return [...range.getClientRects()].map(r=>({top:r.top,bottom:r.bottom,left:r.left,right:r.right,width:r.width,height:r.height}));});
    const style=getComputedStyle(node);
    return [{text:texts.map(child=>child.textContent.trim()).join(' '),tag:node.tagName,
      role:node.matches('.workflow-stage-number')?'marker':node.matches('small')?'metadata':'label',
      ariaHidden:node.getAttribute('aria-hidden'),visible:visible(node),rect:rect(node),textRects:ranges,
      inViewport:ranges.length>0 && ranges.every(within),opacity:opacity(node),
      color:style.color,background:surface?getComputedStyle(surface).backgroundColor:null,
      backgroundSource:surface?{tag:surface.tagName,className:surface.className}:null,
      fontSize:style.fontSize,fontWeight:style.fontWeight,fontFamily:style.fontFamily}];
  });
  const style=getComputedStyle(button);
  return {state:button.getAttribute('aria-current'),name:button.getAttribute('aria-label')||button.textContent.trim(),
    disabled:button.disabled,visible:visible(button),focused:button===document.activeElement,
    inViewport:within(rect(button)),rect:rect(button),opacity:opacity(button),outlineWidth:parseFloat(style.outlineWidth),
    directTextNodeCount:nodes.length,samples:nodes,
    currentInventory:[...document.querySelectorAll('.sidebar button[aria-current]')].map(node=>({
      state:node.getAttribute('aria-current'),disabled:node.disabled,visible:visible(node)})),
    theme:document.documentElement.dataset.theme,viewport:{width:innerWidth,height:innerHeight},scroll:{x:scrollX,y:scrollY},
    documentClientWidth:document.documentElement.clientWidth,documentScrollWidth:document.documentElement.scrollWidth,
    actualOfflineSettings:document.querySelector('#privacy-network-policy')?.value==='offline',
    allToolsOpen:Boolean(document.querySelector('[data-all-tools]')?.open),
    rendererEnvironment:{deviceScaleFactor:devicePixelRatio,locale:navigator.language,
      timezoneId:Intl.DateTimeFormat().resolvedOptions().timeZone,now:Date.now(),random:Math.random()}};
}"""


class ObservationComplete(Exception):
    """Bounded successful stop, not a full runtime-frame verdict."""


def rgb_hex(value: Any) -> str:
    """No assumed background, unmeasured alpha composition or color fallback."""
    match = re.fullmatch(r"rgb\((\d+), (\d+), (\d+)\)", value if isinstance(value, str) else "")
    if not match or any(int(channel) > 255 for channel in match.groups()):
        raise ValueError("navigation colors must be actual opaque computed RGB")
    return "#" + "".join(f"{int(channel):02x}" for channel in match.groups())


def focus_by_tab(page: Any, target: Any) -> None:
    anchor = target.evaluate_handle(r"""node => {
      const candidates=[...document.querySelectorAll('button,input,select,textarea,a[href],[tabindex],summary')]
        .filter(item=>item.tabIndex>=0 && !item.disabled && item.getClientRects().length
          && getComputedStyle(item).visibility==='visible');
      return candidates[candidates.indexOf(node)-1];
    }""")
    try:
        anchor.evaluate("node => { if(!node) throw new Error('missing preceding control'); node.focus(); }")
        page.keyboard.press("Tab")
        if not target.evaluate("node => node===document.activeElement"):
            raise ValueError("actual Tab did not reach the enabled current navigation control")
    finally:
        anchor.dispose()


def validate_observation(observed: dict[str, Any], ratio: Any) -> None:
    inventory = observed["currentInventory"]
    if len(inventory) != 2 or {item["state"] for item in inventory} != set(STATES):
        raise ValueError("actual workflow must supply exactly one current step and one current page")
    if any(item["disabled"] or not item["visible"] for item in inventory):
        raise ValueError("current step/page inventory must be visible and enabled")
    if not all(observed[key] for key in ("visible", "focused", "inViewport", "actualOfflineSettings", "allToolsOpen")):
        raise ValueError("current navigation is not visibly reached in actual settings state")
    if observed["disabled"] or observed["opacity"]["effective"] != 1 or observed["outlineWidth"] < 2:
        raise ValueError("current control disabled/opacity/focus contract differs")
    if observed["documentScrollWidth"] > observed["documentClientWidth"]:
        raise ValueError("current navigation has horizontal document escape")
    samples = observed["samples"]
    expected_roles = {"label", "metadata", "marker"} if observed["state"] == "step" else {"label", "metadata"}
    if observed["directTextNodeCount"] != len(samples) or not samples or {item["role"] for item in samples} != expected_roles:
        raise ValueError("direct current-navigation label/marker/metadata inventory is incomplete")
    for sample in samples:
        if not sample["visible"] or not sample["inViewport"] or sample["opacity"]["effective"] != 1:
            raise ValueError("current navigation text is hidden, clipped or opacity-composited")
        sample["foregroundHex"] = rgb_hex(sample["color"])
        sample["backgroundHex"] = rgb_hex(sample["background"])
        sample["contrastRatio"] = ratio(sample["foregroundHex"], sample["backgroundHex"])
        sample["requiredContrast"] = 4.5
        if sample["contrastRatio"] < 4.5:
            raise ValueError("enabled current-navigation text fails normal-text AA contrast")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observer-commit", required=True)
    parser.add_argument("--producer-commit", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"artifacts/evidence/W1\.A08\.T02\.(?:context|navigation)-captures-[0-9]{2}", args.output):
        raise ValueError("output must be a new canonical task-local capture directory")
    root = Path(__file__).resolve(strict=True).parents[2]
    producer = (root / CHECKOUT).resolve(strict=True)
    if producer != root / CHECKOUT:
        raise ValueError("qualification checkout must not be redirected")
    sys.path.insert(0, str(producer / "tools"))
    import desktop_app_check as desktop
    import product_style_check as style
    from build_manifest import windows_path_locks
    from ui_conformance import confined_path, stable_file_bytes

    for module in (desktop, style):
        if Path(module.__file__).resolve(strict=True) != producer / "tools" / Path(module.__file__).name:
            raise ValueError("observer imported the wrong producer module")
    style._full_commit(root, args.observer_commit)
    style._full_commit(producer, args.producer_commit)
    observer_path = confined_path(root, OBSERVER)
    observer_bytes = stable_file_bytes(root, observer_path)
    observer_sha = hashlib.sha256(observer_bytes).hexdigest()
    observer_blob = style.capture_source_identity(root, args.observer_commit, {OBSERVER: observer_sha})[OBSERVER]

    def snapshot() -> dict[str, Any]:
        if style._git_bytes(producer, "rev-parse", "HEAD").decode().strip() != args.producer_commit:
            raise ValueError("qualification producer HEAD differs or changed")
        if stable_file_bytes(root, observer_path) != observer_bytes:
            raise ValueError("observer changed during observation")
        return style.capture_producer_snapshot(producer, args.producer_commit)

    before = snapshot()
    paths = list(before["inputSha256"])
    for build_root, key in (("apps/desktop/product-dist", "productManifest"), ("apps/desktop/dist", "referenceBuildManifest")):
        paths.extend(f"{build_root}/{name}" for name in before[key]["artifacts"])
        paths.append(f"{build_root}/application-manifest.json")
    selected = [row for row in desktop.qualification_capture_contract(producer)
                if row["surfaceId"] == "settings" and row["role"] == "product"]
    contract = [{**row, "caseId": row["caseId"].replace("workspace:settings:", f"current-navigation:{state}:settings:"),
                 "stateId": f"enabled-current-{state}-text"} for row in selected for state in STATES]
    if len(selected) != 6 or len(contract) != 12:
        raise ValueError("expected exactly six theme/viewport cases and two current states")

    def render(capture: Any) -> tuple[list[str], dict[str, Any]]:
        observations: list[dict[str, Any]] = []
        measured: list[dict[str, Any]] = []
        renderer: dict[str, Any] = {}
        original_record = desktop.ProductStyleQualification.record
        original_keyboard = desktop.exercise_workflow_context_keyboard
        stopped = False

        def record(instance: Any, page: Any, surface_id: str, selector: str) -> None:
            if surface_id != "settings":
                return  # Only skip unrelated matrix sampling, never fixture/runtime transitions.

            def keyboard(observed_page: Any) -> dict[str, int]:
                original_result = original_keyboard(observed_page)
                if original_result != {"buttonCount": 2, "enabledCount": 1, "traversedCount": 1}:
                    raise ValueError("prior context keyboard contract differs")
                disclosure = observed_page.locator("[data-all-tools]")
                opened_for_observation = disclosure.get_attribute("open") is None
                if opened_for_observation:
                    disclosure.locator("summary").click()
                for state in STATES:
                    target = observed_page.locator(f'.sidebar button[aria-current="{state}"]:visible:not(:disabled)')
                    if target.count() != 1:
                        raise ValueError("required actual enabled current navigation state is missing")
                    focus_by_tab(observed_page, target)
                    settled = observed_page.evaluate(SETTLE)
                    observed = target.evaluate(SAMPLE)
                    unchanged = target.evaluate(SAMPLE)
                    if observed != unchanged:
                        raise ValueError("computed navigation sample changed after settled frames")
                    validate_observation(observed, desktop.contrast_ratio)
                    matches = [row for row in contract if row["viewport"] == observed["viewport"]
                               and row["theme"] == observed["theme"] and row["stateId"] == f"enabled-current-{state}-text"]
                    if len(matches) != 1:
                        raise ValueError("observed navigation identity differs from contract")
                    metadata = matches[0]
                    pixels = observed_page.screenshot(full_page=False, animations="disabled", caret="hide", scale="device")
                    if target.evaluate(SAMPLE) != unchanged:
                        raise ValueError("navigation colors or visibility changed during screenshot")
                    observations.append({**metadata, **observed, "settled": settled,
                                         "openedAllToolsForObservation": opened_for_observation,
                                         "reachedByActualTab": True})
                    capture(metadata, pixels)
                # Restore the exact context keyboard/focus behavior expected by the unchanged recorder.
                restored = original_keyboard(observed_page)
                if restored != original_result:
                    raise ValueError("context keyboard state changed after navigation observation")
                return restored

            desktop.exercise_workflow_context_keyboard = keyboard
            try:
                original_record(instance, page, surface_id, selector)
            finally:
                desktop.exercise_workflow_context_keyboard = original_keyboard
            measured.extend(instance.report["cases"])
            renderer.update(instance.report["renderer"])
            raise ObservationComplete()

        desktop.ProductStyleQualification.record = record
        try:
            result = desktop.runtime_frame_errors(producer)
            raise ValueError("runtime returned before bounded settings observation: " + str(bool(result[0])))
        except ObservationComplete:
            stopped = True
        finally:
            desktop.ProductStyleQualification.record = original_record
            desktop.exercise_workflow_context_keyboard = original_keyboard
        errors = []
        if not stopped or len(measured) != 6 or len(observations) != 12:
            errors.append("twelve-state navigation observation did not complete")
        for case in measured:
            errors.extend(desktop.qualification_measurement_errors(case))
        if renderer != {key: before["rendererSettings"][key] for key in ("platform", "playwrightVersion", "browserVersion")}:
            errors.append("actual renderer differs from approved pins")
        return errors, {
            "documentType": "supplemental-current-navigation-contrast-observation",
            "taskId": "W1.A08.T02", "findingId": "W1.A08.T02-visual-03-F01",
            "ok": not errors, "formalTaskApproval": False,
            "observer": {"path": OBSERVER, "commit": args.observer_commit,
                         "gitBlob": observer_blob, "rawSha256": observer_sha},
            "scope": "Actual compiled product in existing deterministic settings workflow adapters; current step/page text at three viewports in both themes. Twelve viewport PNGs plus original six settings geometry/keyboard observations. Not native/Core integration, ordinary-profile evidence, replacement for the 108 matrix, or a full runtime-frame PASS.",
            "boundedRuntimeStop": "Only settings matrix sampling runs. Upstream fixture transitions are unchanged; ObservationComplete unwinds existing browser cleanup after settings. Whole-suite outcomes are not asserted.",
            "contrastPolicy": "All visible direct label, marker and metadata text of enabled current controls must have opaque computed RGB, effective opacity1 and contrast >=4.5 using producer desktop_app_check.contrast_ratio. aria-hidden text is included; no decorative/disabled exemption is substituted.",
            "renderer": renderer, "navigationObservations": observations,
            "settingsMeasurements": measured, "measurementErrors": errors,
            "producerStableBeforeAfter": True,
            "publication": "Existing guarded write_capture_bundle: exact 12-PNG inventory, exclusive create, path/file holds, valid PNGs, before/after source equality and manifest last. Failed runs never receive an accepted completion manifest.",
        }

    with windows_path_locks([observer_path, *[confined_path(producer, path) for path in paths]], directories=False):
        if snapshot() != before:
            raise ValueError("producer changed before input locking")
        manifest = style.write_capture_bundle(root, args.output, contract, snapshot, render)
    print(json.dumps({"ok": True, "manifest": manifest.relative_to(root).as_posix(),
                      "producerCommit": args.producer_commit, "observerCommit": args.observer_commit,
                      "formalTaskApproval": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"ok": False, "errorType": type(error).__name__,
                          "completionManifestAccepted": False, "formalTaskApproval": False}))
        raise SystemExit(1) from None
