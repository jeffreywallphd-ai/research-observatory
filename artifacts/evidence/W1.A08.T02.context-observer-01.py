"""Supplemental actual-product workflow-context observation, never task approval.

Uses the unchanged ddba5f5f qualification checkout and its existing fixture
adapters. Only the settings measurement hook is observed; the runtime is
deliberately stopped there. This does not report a full runtime-frame PASS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


PRODUCER = "ddba5f5f21298f5f292a73eddee52ceff74f894f"
OBSERVER = "artifacts/evidence/W1.A08.T02.context-observer-01.py"
OUTPUT = "artifacts/evidence/W1.A08.T02.context-captures-01"
CHECKOUT = ".local/qualification-worktrees/w1-a08-t02"

CONTEXT = r"""() => {
  const node = document.querySelector('main > [data-workflow-context]');
  const rect = element => { const r = element.getBoundingClientRect();
    return {top:r.top,bottom:r.bottom,left:r.left,right:r.right,width:r.width,height:r.height}; };
  const visible = element => element.getClientRects().length && getComputedStyle(element).visibility === 'visible';
  const inViewport = element => {const r = rect(element); return r.top >= -.5 && r.bottom <= innerHeight + .5
    && r.left >= -.5 && r.right <= innerWidth + .5;};
  return {
    contextPresent: Boolean(node), contextText: node?.textContent?.trim(),
    contextRect: node ? rect(node) : null,
    controls: node ? [...node.querySelectorAll('button')].filter(visible).map(element => {
      const style = getComputedStyle(element);
      return {name:element.textContent.trim(),disabled:element.disabled,focused:element===document.activeElement,
        className:element.className,rect:rect(element),inViewport:inViewport(element),
        minHeight:parseFloat(style.minHeight),padding:parseFloat(style.paddingInlineStart),
        radius:parseFloat(style.borderRadius),outlineWidth:parseFloat(style.outlineWidth),
        fontFamily:style.fontFamily,fontSize:style.fontSize,color:style.color,background:style.backgroundColor};
    }) : [],
    scroll:{x:scrollX,y:scrollY},viewport:{width:innerWidth,height:innerHeight},
    theme:document.documentElement.dataset.theme,
    documentClientWidth:document.documentElement.clientWidth,
    documentScrollWidth:document.documentElement.scrollWidth,
    actualOfflineSettings:document.querySelector('#privacy-network-policy')?.value === 'offline',
    rendererEnvironment:{deviceScaleFactor:devicePixelRatio,locale:navigator.language,
      timezoneId:Intl.DateTimeFormat().resolvedOptions().timeZone,
      now:Date.now(),random:Math.random()}
  };
}"""


class ObservationComplete(Exception):
    """Intentional bounded stop; not evidence that the full frame suite passed."""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observer-commit", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve(strict=True).parents[2]
    producer = (root / CHECKOUT).resolve(strict=True)
    if producer != root / CHECKOUT:
        raise ValueError("qualification checkout must not be redirected")
    sys.path.insert(0, str(producer / "tools"))
    import desktop_app_check as desktop
    import product_style_check as style
    from build_manifest import confined_path, stable_file_bytes, windows_path_locks

    for module in (desktop, style):
        if Path(module.__file__).resolve(strict=True) != producer / "tools" / Path(module.__file__).name:
            raise ValueError("observer imported the wrong producer module")
    style._full_commit(root, args.observer_commit)
    observer_path = confined_path(root, OBSERVER)
    observer_bytes = stable_file_bytes(root, observer_path)
    observer_sha = hashlib.sha256(observer_bytes).hexdigest()
    observer_blob = style.capture_source_identity(root, args.observer_commit, {OBSERVER: observer_sha})[OBSERVER]

    def snapshot() -> dict[str, Any]:
        if style._git_bytes(producer, "rev-parse", "HEAD").decode().strip() != PRODUCER:
            raise ValueError("qualification producer HEAD changed")
        if stable_file_bytes(root, observer_path) != observer_bytes:
            raise ValueError("observer changed during observation")
        return style.capture_producer_snapshot(producer, PRODUCER)

    before = snapshot()
    paths = list(before["inputSha256"])
    for build_root, key in (("apps/desktop/product-dist", "productManifest"), ("apps/desktop/dist", "referenceBuildManifest")):
        paths.extend(f"{build_root}/{name}" for name in before[key]["artifacts"])
        paths.append(f"{build_root}/application-manifest.json")
    selected = [row for row in desktop.qualification_capture_contract(producer)
                if row["surfaceId"] == "settings" and row["role"] == "product"]
    contract = [{**row, "caseId": row["caseId"].replace("workspace:settings:", "workflow-context:settings:"),
                 "stateId": "supporting-tool-context-before-workspace-autofocus"} for row in selected]
    if len(contract) != 6:
        raise ValueError("expected exactly six theme/viewport cases")

    def render(capture: Any) -> tuple[list[str], dict[str, Any]]:
        observations: list[dict[str, Any]] = []
        measured: list[dict[str, Any]] = []
        renderer: dict[str, Any] = {}
        original_record = desktop.ProductStyleQualification.record
        original_keyboard = desktop.exercise_workflow_context_keyboard
        stopped = False

        def record(instance: Any, page: Any, surface_id: str, selector: str) -> None:
            if surface_id != "settings":
                return  # Skip unrelated matrix sampling, not fixture/runtime state transitions.

            def keyboard(observed_page: Any) -> dict[str, int]:
                result = original_keyboard(observed_page)
                observed_page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
                observation = observed_page.evaluate(CONTEXT)
                matches = [row for row in contract if row["viewport"] == observation["viewport"]
                           and row["theme"] == observation["theme"]]
                if len(matches) != 1 or not observation["actualOfflineSettings"]:
                    raise ValueError("actual settings/context state differs from the observation contract")
                controls = observation["controls"]
                if result != {"buttonCount": 2, "enabledCount": 1, "traversedCount": 1} or len(controls) != 2:
                    raise ValueError("context inventory or real Tab traversal differs")
                if not (controls[0]["name"].startswith("Next step") and controls[0]["disabled"]
                        and controls[1]["name"].startswith("Return to current step")
                        and not controls[1]["disabled"] and controls[1]["focused"]):
                    raise ValueError("Next/Return authority or focus differs")
                for control in controls:
                    if not (control["inViewport"] and control["minHeight"] == 40
                            and control["rect"]["height"] >= 40 and control["padding"] == 16
                            and control["radius"] == 10 and "ro-button" in control["className"].split()):
                        raise ValueError("actual context control geometry or visibility differs")
                if controls[1]["outlineWidth"] < 2 or observation["documentScrollWidth"] > observation["documentClientWidth"]:
                    raise ValueError("context focus or horizontal containment failed")
                metadata = matches[0]
                observations.append({**metadata, **observation, "workflowContextKeyboard": result})
                capture(metadata, observed_page.screenshot(full_page=False, animations="disabled", caret="hide", scale="device"))
                return result

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
            raise ValueError("runtime returned before the bounded settings observation: " + str(bool(result[0])))
        except ObservationComplete:
            stopped = True
        finally:
            desktop.ProductStyleQualification.record = original_record
            desktop.exercise_workflow_context_keyboard = original_keyboard
        errors = []
        if not stopped or len(measured) != 6 or len(observations) != 6:
            errors.append("supplemental six-case observation did not complete")
        for case in measured:
            errors.extend(desktop.qualification_measurement_errors(case))
        if renderer != {key: before["rendererSettings"][key] for key in ("platform", "playwrightVersion", "browserVersion")}:
            errors.append("actual renderer does not match approved pins")
        return errors, {
            "documentType": "supplemental-workflow-context-observation",
            "taskId": "W1.A08.T02", "ok": not errors, "formalTaskApproval": False,
            "observer": {"path": OBSERVER, "commit": args.observer_commit,
                         "gitBlob": observer_blob, "rawSha256": observer_sha},
            "scope": "Actual built product in unchanged qualification fixture adapters; six settings context captures immediately after real Tab and before workspace autofocus. Not native/Core integration, ordinary-profile evidence, the full108 capture matrix, or a full runtime-frame PASS.",
            "boundedRuntimeStop": "ProductStyleQualification.record completes only settings sampling, then ObservationComplete unwinds the existing browser cleanup. Other matrix sampling is skipped; upstream fixture transitions remain unchanged. Their whole-suite outcomes are not asserted here.",
            "renderer": renderer, "contextObservations": observations,
            "settingsMeasurements": measured, "measurementErrors": errors,
            "producerStableBeforeAfter": True,
            "publication": "Existing write_capture_bundle: exact six PNG inventory, exclusive create, held path/file guards, PNG validation, snapshot equality, manifest last; interrupted runs have no completion manifest.",
        }

    with windows_path_locks([observer_path, *[confined_path(producer, path) for path in paths]], directories=False):
        if snapshot() != before:
            raise ValueError("producer changed before locking")
        manifest = style.write_capture_bundle(root, OUTPUT, contract, snapshot, render)
    print(json.dumps({"ok": True, "manifest": manifest.relative_to(root).as_posix(),
                      "producerCommit": PRODUCER, "observerCommit": args.observer_commit,
                      "formalTaskApproval": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        # Avoid publishing local account/worktree paths from browser/subprocess diagnostics.
        print(json.dumps({"ok": False, "errorType": type(error).__name__,
                          "completionManifestAccepted": False, "formalTaskApproval": False}))
        raise SystemExit(1) from None
