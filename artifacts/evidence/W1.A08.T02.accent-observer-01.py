"""Observe two actual product accent-text states; never approve the task.

Reuse the producer's build/source checks, fixture adapters, Windows file holds
and exclusive capture publisher. Previous observers and bundles are immutable.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import sys
from typing import Any


OBSERVER = "artifacts/evidence/W1.A08.T02.accent-observer-01.py"
CHECKOUT = ".local/qualification-worktrees/w1-a08-t02"
ADAPTER = "tests/desktop/fixtures/task_center_interactions.js"
CONSUMERS = {"eyebrow": ".eyebrow", "skip-link": ".skip-link"}
TEXT = {"eyebrow": "Application Settings", "skip-link": "Skip to project home"}

SAMPLE = r"""node => {
  const rect = r => ({top:r.top,bottom:r.bottom,left:r.left,right:r.right,width:r.width,height:r.height});
  const within = r => r.width>0 && r.height>0 && r.top>=0 && r.bottom<=innerHeight
    && r.left>=0 && r.right<=innerWidth;
  const style=getComputedStyle(node), box=rect(node.getBoundingClientRect());
  let surface=node, effectiveOpacity=1, effectiveVisibility=true;
  const ancestors=[];
  for(let parent=node;parent;parent=parent.parentElement) {
    const s=getComputedStyle(parent);
    effectiveOpacity*=Number(s.opacity);
    effectiveVisibility=effectiveVisibility && s.display!=='none' && s.visibility==='visible';
    ancestors.push({tag:parent.tagName,display:s.display,visibility:s.visibility,opacity:Number(s.opacity)});
  }
  while(surface && getComputedStyle(surface).backgroundColor==='rgba(0, 0, 0, 0)') surface=surface.parentElement;
  const walker=document.createTreeWalker(node,NodeFilter.SHOW_TEXT), textRects=[];
  for(let text=walker.nextNode();text;text=walker.nextNode()) {
    if(!text.textContent.trim())continue;
    const range=document.createRange();range.selectNode(text);
    textRects.push(...[...range.getClientRects()].map(rect));
  }
  return {text:node.textContent.trim(),tag:node.tagName,color:style.color,
    background:surface?getComputedStyle(surface).backgroundColor:null,
    backgroundSource:surface?{tag:surface.tagName,className:surface.className}:null,
    rect:box,textRects,nonempty:box.width>0 && box.height>0 && textRects.length>0,
    inViewport:within(box) && textRects.length>0 && textRects.every(within),
    effectiveVisibility,effectiveOpacity,ancestors,
    visible:effectiveVisibility && effectiveOpacity>0 && within(box) && textRects.length>0 && textRects.every(within),
    disabled:node.matches(':disabled') || node.getAttribute('aria-disabled')==='true',
    focused:node===document.activeElement,outlineWidth:parseFloat(style.outlineWidth),
    fontSize:style.fontSize,fontWeight:style.fontWeight,fontFamily:style.fontFamily,transform:style.transform,
    href:node.getAttribute('href'),theme:document.documentElement.dataset.theme,
    viewport:{width:innerWidth,height:innerHeight},scroll:{x:scrollX,y:scrollY},
    documentClientWidth:document.documentElement.clientWidth,documentScrollWidth:document.documentElement.scrollWidth,
    applicationReady:document.body.dataset.applicationReady==='true',
    applicationSettingsVisible:Boolean(document.querySelector('[data-application-settings]')?.getClientRects().length),
    environment:{deviceScaleFactor:devicePixelRatio,locale:navigator.language,
      timezoneId:Intl.DateTimeFormat().resolvedOptions().timeZone,now:Date.now(),random:Math.random()}};
}"""

SETTLE = "async node => { const sample = (" + SAMPLE + r""");
  let previous='',stable=0;
  for(let frame=0;frame<120;frame++) {
    await new Promise(requestAnimationFrame);
    const current=JSON.stringify(sample(node)), animations=document.getAnimations();
    const running=animations.filter(a=>a.playState==='running').length;
    const pending=animations.filter(a=>a.pending).length;
    stable=current===previous && !running && !pending ? stable+1 : 0;
    if(stable>=3)return {frames:frame+1,stableFrames:stable,runningAnimations:running,pendingAnimations:pending};
    previous=current;
  }
  throw new Error('accent text/focus geometry did not settle');
}"""

DETERMINISTIC_CLOCK = """
Date = class extends Date { constructor(...a){ super(...(a.length ? a : ['2026-08-08T12:00:00Z'])); }
  static now(){ return 1786190400000; } };
Math.random = () => 0.25;
"""


def opaque_hex(value: Any) -> str:
    match = re.fullmatch(r"rgb\((\d+), (\d+), (\d+)\)", value if isinstance(value, str) else "")
    if not match or any(int(channel) > 255 for channel in match.groups()):
        raise ValueError("accent colors must be actual opaque computed RGB")
    return "#" + "".join(f"{int(channel):02x}" for channel in match.groups())


def validate_sample(observed: dict[str, Any], consumer: str, metadata: dict[str, Any], ratio: Any) -> dict[str, Any]:
    if consumer not in CONSUMERS or observed["text"] != TEXT[consumer]:
        raise ValueError("actual accent consumer identity differs")
    if observed["theme"] != metadata["theme"] or observed["viewport"] != metadata["viewport"]:
        raise ValueError("actual accent theme/viewport differs")
    if not all(observed[key] for key in (
        "nonempty", "inViewport", "effectiveVisibility", "visible", "applicationReady", "applicationSettingsVisible"
    )) or observed["disabled"] or observed["effectiveOpacity"] != 1:
        raise ValueError("accent consumer is hidden, clipped, disabled or opacity-composited")
    if observed["documentScrollWidth"] > observed["documentClientWidth"]:
        raise ValueError("accent observation has horizontal document escape")
    if consumer == "skip-link" and (
        observed["tag"] != "A" or observed["href"] != "#main-content"
        or not observed["focused"] or observed["outlineWidth"] < 2
    ):
        raise ValueError("actual skip link is not visibly keyboard focused with its unchanged target")
    foreground, background = opaque_hex(observed["color"]), opaque_hex(observed["background"])
    measured = ratio(foreground, background)
    if measured < 4.5:
        raise ValueError("accent text fails normal-text AA contrast")
    return {"foregroundHex": foreground, "backgroundHex": background, "contrastRatio": measured, "requiredContrast": 4.5}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observer-commit", required=True)
    parser.add_argument("--producer-commit", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"artifacts/evidence/W1\.A08\.T02\.accent-captures-[0-9]{2}", args.output):
        raise ValueError("output must be a new canonical task-local accent capture directory")
    root = Path(__file__).resolve(strict=True).parents[2]
    producer = (root / CHECKOUT).resolve(strict=True)
    if producer != root / CHECKOUT:
        raise ValueError("qualification checkout must not be redirected")
    sys.path.insert(0, str(producer / "tools"))
    import desktop_app_check as desktop
    import product_style_check as style
    from build_manifest import windows_path_locks
    from ui_conformance import confined_path, font_face_available, stable_file_bytes

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
            raise ValueError("observer source changed")
        return style.capture_producer_snapshot(producer, args.producer_commit)

    before = snapshot()
    visual = before["rendererSettings"]
    if platform.system() != "Windows" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise ValueError("accent observation requires Windows x64")
    installed_playwright = importlib.metadata.version("playwright")
    if installed_playwright != visual["playwrightVersion"]:
        raise ValueError("Playwright differs from the approved renderer pin")
    paths = list(before["inputSha256"])
    if ADAPTER not in paths:
        raise ValueError("actual fixture adapter is absent from the source snapshot")
    for build_root, key in (("apps/desktop/product-dist", "productManifest"), ("apps/desktop/dist", "referenceBuildManifest")):
        paths.extend(f"{build_root}/{name}" for name in before[key]["artifacts"])
        paths.append(f"{build_root}/application-manifest.json")
    selected = [row for row in desktop.qualification_capture_contract(producer)
                if row["surfaceId"] == "application-settings" and row["role"] == "product"]
    contract = [{**row, "caseId": row["caseId"].replace("workspace:", f"accent:{consumer}:"),
                 "stateId": f"visible-{consumer}-text"} for row in selected for consumer in CONSUMERS]
    if len(selected) != 6 or len(contract) != 12 or {
        (row["width"], row["height"], row["theme"]) for row in selected
    } != {(w, h, theme) for w, h in ((1440, 900), (1280, 720), (720, 450)) for theme in ("light", "dark")}:
        raise ValueError("expected exactly six theme/viewport cases and two accent consumers")

    def render(capture: Any) -> tuple[list[str], dict[str, Any]]:
        from playwright.sync_api import sync_playwright

        document = desktop.inline_product_index(producer)
        adapter = stable_file_bytes(producer, confined_path(producer, ADAPTER)).decode("utf-8")
        adapter = adapter.replace("__WORKFLOW_CATALOG__", desktop.core_workflow_catalog_json(producer))
        adapter += desktop.DIRECTORY_PICKER_FIXTURE
        observations: list[dict[str, Any]] = []
        blocked_requests = 0
        page_errors = 0
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=[
                "--disable-font-subpixel-positioning", "--disable-lcd-text", "--force-color-profile=srgb"
            ])
            try:
                renderer = {"platform": "windows-x64", "playwrightVersion": installed_playwright,
                            "browserVersion": browser.version}
                if browser.version != visual["browserVersion"]:
                    raise ValueError("Chromium differs from the approved renderer pin")
                for case in selected:
                    context = browser.new_context(viewport=case["viewport"], color_scheme=case["theme"],
                        device_scale_factor=visual["deviceScaleFactor"], locale=visual["locale"],
                        timezone_id=visual["timezoneId"], reduced_motion=visual["reducedMotion"])
                    try:
                        context.add_init_script(DETERMINISTIC_CLOCK + adapter)

                        def route_request(route: Any) -> None:
                            nonlocal blocked_requests
                            if route.request.url == "http://tauri.localhost/index.html":
                                route.fulfill(status=200, content_type="text/html", body=document)
                            else:
                                blocked_requests += 1
                                route.abort()

                        def record_error(_: Any) -> None:
                            nonlocal page_errors
                            page_errors += 1

                        context.route("**/*", route_request)
                        page = context.new_page()
                        page.on("pageerror", record_error)
                        page.goto("http://tauri.localhost/index.html")
                        page.wait_for_function("document.body.dataset.applicationReady === 'true'")
                        page.get_by_role("button", name="Local profile", exact=True).click()
                        page.locator("[data-application-settings] .eyebrow").wait_for(state="visible")
                        page.locator("html").evaluate("(node, theme) => node.dataset.theme=theme", case["theme"])
                        page.evaluate("document.fonts.ready")
                        fonts = {font: font_face_available(page, font) for font in visual["requiredFonts"]}
                        if not all(fonts.values()):
                            raise ValueError("required renderer font is unavailable")
                        for consumer, selector in CONSUMERS.items():
                            target = page.locator(selector)
                            if target.count() != 1:
                                raise ValueError("expected exactly one actual accent consumer")
                            reverse_tabs = 0
                            if consumer == "eyebrow":
                                target.scroll_into_view_if_needed()
                            else:
                                for reverse_tabs in range(1, 61):
                                    page.keyboard.press("Shift+Tab")
                                    if target.evaluate("node => node===document.activeElement"):
                                        break
                                else:
                                    raise ValueError("actual reverse Tab did not reach the skip link")
                            settled = target.evaluate(SETTLE)
                            observed = target.evaluate(SAMPLE)
                            if target.evaluate(SAMPLE) != observed:
                                raise ValueError("accent sample changed after settled frames")
                            metadata = next(row for row in contract if row["theme"] == case["theme"]
                                and row["viewport"] == case["viewport"] and row["stateId"] == f"visible-{consumer}-text")
                            colors = validate_sample(observed, consumer, metadata, desktop.contrast_ratio)
                            expected_environment = {"deviceScaleFactor": visual["deviceScaleFactor"],
                                "locale": visual["locale"], "timezoneId": visual["timezoneId"],
                                "now": 1786190400000, "random": 0.25}
                            if observed["environment"] != expected_environment:
                                raise ValueError("actual renderer environment differs from the pinned fixture")
                            pixels = page.screenshot(full_page=False, animations="disabled", caret="hide", scale="device")
                            if target.evaluate(SAMPLE) != observed:
                                raise ValueError("accent sample changed during screenshot")
                            observations.append({**metadata, **observed, **colors, "consumer": consumer,
                                "fonts": fonts, "settled": settled, "reverseTabCount": reverse_tabs,
                                "reachedByActualShiftTab": consumer == "skip-link"})
                            capture(metadata, pixels)
                    finally:
                        context.close()
            finally:
                browser.close()
        if len(observations) != 12 or blocked_requests or page_errors:
            raise ValueError("accent observation inventory or browser error/request boundary failed")
        return [], {
            "documentType": "supplemental-accent-text-contrast-observation", "taskId": "W1.A08.T02",
            "findingId": "W1.A08.T02-visual-05-F01", "ok": True, "formalTaskApproval": False,
            "observer": {"path": OBSERVER, "commit": args.observer_commit,
                "gitBlob": observer_blob, "rawSha256": observer_sha},
            "scope": "Actual compiled product plus unchanged task_center_interactions and DIRECTORY_PICKER_FIXTURE; Local profile opens actual Application Settings. Separate eyebrow and real Shift+Tab-focused skip-link observations in both themes at all three required viewports. Not native/Core, ordinary-profile, the complete runtime workflow suite or a replacement for the 108-image matrix.",
            "renderer": renderer, "observations": observations, "blockedRequestCount": blocked_requests,
            "pageErrorCount": page_errors, "producerStableBeforeAfter": True,
            "publication": "Existing write_capture_bundle exclusive 12-PNG inventory, Windows input/output holds, valid dimensions, before/after producer equality and manifest last; immutable delivery authentication remains a later read_capture_bundle operation.",
        }

    with windows_path_locks([observer_path, *[confined_path(producer, path) for path in paths]], directories=False):
        if snapshot() != before:
            raise ValueError("producer changed before inputs were held")
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
