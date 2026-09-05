"""Focused built-renderer folder UX proof; native outcomes are explicit doubles."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REPORTS = REPO / "artifacts/evidence"
sys.path.insert(0, str(REPO / "tools"))

from desktop_app_check import core_workflow_catalog_json, inline_product_index, product_build_errors  # noqa: E402
from playwright.sync_api import expect, sync_playwright  # noqa: E402

NATIVE_DOUBLE = r"""
(() => {
  const catalog = __CATALOG__;
  const f = window.folderFixture = {
    calls: [], defaults: [], pickers: [], callbacks: [], locked: false, sequence: 0,
    deferredDefault: __DEFERRED__, parent: 'C:/Research',
  };
  const snapshot = () => ({
    schemaVersion: '1.0', state: f.locked ? 'locked' : 'unlocked',
    signInMode: 'windows-password', policyRevision: 1, profileName: null,
    inactivityTimeoutMinutes: 0, configurationState: 'valid',
    reason: f.locked ? 'manual' : null, retryAfterSeconds: 0,
    auditSequence: f.sequence,
    threatDisclosure: 'Application-session protection only; this is not Windows-account isolation.',
  });
  const traceId = 'a'.repeat(32);
  window.__TAURI_INTERNALS__ = {
    transformCallback: callback => { f.callbacks.push(callback); return f.callbacks.length - 1; },
    unregisterCallback: () => {},
    invoke: async (command, args) => {
      if (command === 'application_lock_status') return snapshot();
      if (command === 'application_lock_unlock') {
        f.locked = false; f.sequence++;
        return {schemaVersion:'1.0', outcome:'succeeded',
          reasonCode:'RO-LOCK-UNLOCKED', snapshot:snapshot()};
      }
      if (command === 'application_lock_activity' || command === 'plugin:event|unlisten') return;
      if (command === 'plugin:event|listen') { f.listener = args.handler; return 1; }
      if (command === 'core_runtime_status' || command === 'core_runtime_start')
        return {state: 'ready', attempt: 1, retryAvailable: false, diagnosticReference: null};
      if (command === 'default_project_parent') {
        if (!f.deferredDefault) { f.defaults.push(null); return {status: 'available', path: f.parent}; }
        return await new Promise(resolve => f.defaults.push(resolve));
      }
      if (command === 'choose_project_directory')
        return await new Promise(resolve => f.pickers.push({request: args.request, resolve}));
      if (command === 'core_api_request') {
        const request = args.request;
        if (request.path === '/workflow-profiles/catalog')
          return {status: 200, contentType: 'application/json', traceId, etag: null, body: JSON.stringify(catalog)};
        f.calls.push(request);
        return {status: 409, contentType: 'application/problem+json', traceId, etag: null,
          body: JSON.stringify({type: 'urn:research-observatory:problem:project-already-exists',
            title: 'Destination exists', status: 409,
            detail: 'Synthetic destination already exists.', code: 'RO-CORE-PROJECT-ALREADY-EXISTS',
            traceId, retryable: false, remediation: 'Choose another project name or parent.'})};
      }
      throw Error('Unexpected test command: ' + command);
    },
  };
  f.lock = () => {
    f.locked = true; f.sequence++;
    f.callbacks[f.listener]?.({event:'application-lock-changed', id:1, payload:snapshot()});
  };
})();
"""


def report_target(path: Path) -> Path:
    candidate = path if path.is_absolute() else REPO / path
    if ".." in candidate.parts or candidate.parent != REPORTS:
        raise ValueError("Report scope denied")
    if not re.fullmatch(r"W1\.A09\.T03\.renderer-check-01\.[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\.json", candidate.name):
        raise ValueError("Report namespace denied")
    if candidate.exists():
        raise ValueError("Report already exists")
    return candidate


def publish_report(path: Path, payload: dict) -> None:
    path = report_target(path)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2)
        stream.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report_path = report_target(args.report)
    runner_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    errors = product_build_errors(REPO)
    if errors:
        raise AssertionError(errors)
    manifest = REPO / "apps/desktop/product-dist/application-manifest.json"
    manifest_hash = hashlib.sha256(manifest.read_bytes()).hexdigest()
    visual = json.loads((REPO / "verification/extensions/desktop-ui.json").read_text())["visual"]
    assert importlib.metadata.version("playwright") == visual["playwrightVersion"]
    document = inline_product_index(REPO)
    catalog = core_workflow_catalog_json(REPO)
    outcomes: dict[str, object] = {}
    network: list[str] = []
    page_errors: list[str] = []
    with sync_playwright() as driver:
        browser = driver.chromium.launch(
            headless=True,
            args=[
                "--disable-font-subpixel-positioning",
                "--disable-lcd-text",
                "--force-color-profile=srgb",
            ],
        )
        assert browser.version == visual["browserVersion"]

        def open_page(*, deferred: bool = False, theme: str = "light", width: int = 1440, height: int = 900):
            context = browser.new_context(
                viewport={"width": width, "height": height},
                device_scale_factor=visual["deviceScaleFactor"],
                locale=visual["locale"],
                timezone_id=visual["timezoneId"],
                reduced_motion="reduce",
                color_scheme=theme,
            )
            context.add_init_script(
                NATIVE_DOUBLE.replace("__CATALOG__", catalog).replace("__DEFERRED__", json.dumps(deferred))
            )
            context.add_init_script("localStorage.setItem('research-observatory.theme', " + json.dumps(theme) + ");")

            def route(request):
                if request.request.url in {"http://tauri.localhost/", "http://tauri.localhost/index.html"}:
                    request.fulfill(status=200, content_type="text/html; charset=utf-8", body=document)
                else:
                    network.append(request.request.url)
                    request.abort()

            context.route("**/*", route)
            page = context.new_page()
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.goto("http://tauri.localhost/")
            page.wait_for_selector("[data-application-ready]")
            disclosure = page.locator("[data-all-tools]")
            if disclosure.get_attribute("open") is None:
                disclosure.locator("summary").click()
            disclosure.get_by_role("button", name="Local projects", exact=True).click()
            page.wait_for_selector("#project-parent-directory")
            page.wait_for_function("folderFixture.defaults.length > 0")
            return context, page

        context, page = open_page()
        expect(page.locator("#project-parent-directory-location")).to_have_text("C:/Research")
        page.locator("#project-display-name").fill("Default-only study")
        page.locator("#project-research-objective").fill("Synthetic default-only submission.")
        page.locator("#project-primary-use-case").select_option("theory-synthesis")
        expect(page.locator("#project-destination")).to_have_text("C:/Research/default-only-study")
        assert page.evaluate("folderFixture.calls.length") == 0
        assert page.evaluate("folderFixture.pickers.length") == 0
        page.get_by_role("button", name="Create project", exact=True).click()
        page.wait_for_function("folderFixture.calls.length === 1")
        default_request = page.evaluate("folderFixture.calls[0]")
        assert default_request["path"] == "/projects" and default_request["method"] == "POST"
        default_body = json.loads(default_request["body"])
        assert default_body["parentDirectory"] == "C:/Research"
        assert default_body["directoryName"] == "default-only-study"
        assert page.evaluate("folderFixture.pickers.length") == 0
        outcomes["explicitDefaultOnlyCreateWithoutChooser_nativeAndCoreDoubles"] = True
        context.close()

        context, page = open_page()
        expect(page.locator("#project-parent-directory-location")).to_have_text("C:/Research")
        assert (
            page.locator("input#project-parent-directory,input#project-root,input#project-directory-name").count() == 0
        )
        assert page.evaluate("folderFixture.calls.length") == 0
        page.locator("#project-display-name").fill("Crème Study")
        page.locator("#project-research-objective").fill("Synthetic first line.\nSynthetic second line.")
        page.locator("#project-primary-use-case").select_option("theory-synthesis")
        before_form = page.locator("#project-research-objective").input_value()
        parent_button = page.locator("#project-parent-directory-choose")
        parent_button.focus()
        page.keyboard.press("Enter")
        page.wait_for_function("folderFixture.pickers.length === 1")
        expect(page.locator("#project-root-choose")).to_be_disabled()
        page.evaluate("folderFixture.pickers[0].resolve({status:'cancelled'})")
        expect(parent_button).to_be_focused()
        expect(page.locator("#project-parent-directory-location")).to_have_text("C:/Research")
        assert page.locator("#project-research-objective").input_value() == before_form
        assert page.evaluate("folderFixture.calls.length") == 0
        parent_button.click()
        page.wait_for_function("folderFixture.pickers.length === 2")
        page.evaluate("folderFixture.pickers[1].resolve({status:'selected',path:'C:/研究 Folder'})")
        expect(page.locator("#project-parent-directory-location")).to_have_text("C:/研究 Folder")
        expect(page.locator("#project-destination")).to_have_text("C:/研究 Folder/creme-study")
        assert page.evaluate("folderFixture.calls.length") == 0
        page.get_by_role("button", name="Create project", exact=True).click()
        expect(page.get_by_text("The destination already exists", exact=True)).to_be_visible()
        first = page.evaluate("JSON.stringify(folderFixture.calls)")
        assert len(json.loads(first)) == 1
        page.get_by_role("button", name="Create project", exact=True).click()
        page.wait_for_function("folderFixture.calls.length === 2")
        assert page.evaluate("JSON.stringify(folderFixture.calls[0]) === JSON.stringify(folderFixture.calls[1])")
        outcomes["defaultSelectionCancellationStableCollisionRetry"] = True
        context.close()

        for result_first in (False, True):
            for status in ("cancelled", "failed", "unavailable"):
                context, page = open_page(deferred=True)
                page.locator("#project-parent-directory-choose").click()
                page.wait_for_function("folderFixture.pickers.length === 1")
                if not result_first:
                    page.evaluate("folderFixture.defaults[0]({status:'available',path:'C:/Discarded'})")
                page.evaluate("status => folderFixture.pickers[0].resolve({status})", status)
                page.wait_for_function("folderFixture.defaults.length === 2")
                if result_first:
                    page.evaluate("folderFixture.defaults[0]({status:'available',path:'C:/Stale'})")
                page.evaluate("folderFixture.defaults[1]({status:'available',path:'C:/Recovered'})")
                expect(page.locator("#project-parent-directory-location")).to_have_text("C:/Recovered")
                assert page.evaluate("folderFixture.calls.length") == 0
                context.close()
        outcomes["cancelFailureDefaultRaces"] = 6

        context, page = open_page(deferred=True)
        page.locator("#project-parent-directory-choose").click()
        page.wait_for_function("folderFixture.pickers.length === 1")
        page.evaluate("folderFixture.pickers[0].resolve({status:'selected',path:'C:/Chosen'})")
        expect(page.locator("#project-parent-directory-location")).to_have_text("C:/Chosen")
        page.evaluate("folderFixture.defaults[0]({status:'available',path:'C:/Late'})")
        expect(page.locator("#project-parent-directory-location")).to_have_text("C:/Chosen")
        page.locator("#project-display-name").fill("Protected synthetic draft")
        page.locator("#project-root-choose").click()
        page.wait_for_function("folderFixture.pickers.length === 2")
        page.evaluate("folderFixture.lock()")
        page.wait_for_selector("[data-application-locked]")
        page.evaluate("folderFixture.pickers[1].resolve({status:'selected',path:'C:/Late Private'})")
        assert page.locator("[data-projects-workspace]").count() == 0
        assert "Protected synthetic draft" not in page.locator("body").inner_text()
        assert "C:/Chosen" not in page.locator("body").inner_text()
        assert "C:/Late Private" not in page.locator("body").inner_text()
        assert page.evaluate("folderFixture.calls.length") == 0
        page.evaluate("folderFixture.deferredDefault = false")
        page.get_by_role("button", name="Unlock with Windows password", exact=True).click()
        expect(page.locator("[data-application-locked]")).to_have_count(0)
        page.wait_for_selector("[data-application-ready]")
        disclosure = page.locator("[data-all-tools]")
        if disclosure.get_attribute("open") is None:
            disclosure.locator("summary").click()
        disclosure.get_by_role("button", name="Local projects", exact=True).click()
        expect(page.locator("#project-display-name")).to_have_value("")
        expect(page.locator("#project-research-objective")).to_have_value("")
        expect(page.locator("#project-parent-directory-location")).to_have_text("C:/Research")
        expect(page.locator("#project-root-location")).to_have_text("No folder selected")
        assert page.evaluate("folderFixture.calls.length") == 0
        outcomes["chosenOverrideAndLockDiscard"] = True
        outcomes["freshUnlockDoesNotRestoreProtectedFormOrOpenProject"] = True
        context.close()

        geometry = []
        for theme in ("light", "dark"):
            for width, height in ((1440, 900), (1280, 720), (720, 450)):
                context, page = open_page(theme=theme, width=width, height=height)
                page.locator("#project-parent-directory-choose").click()
                page.wait_for_function("folderFixture.pickers.length === 1")
                long_path = "C:/" + "研究 long folder/" * 50
                page.evaluate("path => folderFixture.pickers[0].resolve({status:'selected',path})", long_path)
                expect(page.locator("#project-parent-directory-location")).to_have_text(long_path)
                values = page.locator("#project-parent-directory-location").evaluate("""element => ({
                    scrollWidth: document.documentElement.scrollWidth, viewport: innerWidth,
                    outputWidth: element.getBoundingClientRect().width, wrap: getComputedStyle(element).overflowWrap,
                    selectable: getComputedStyle(element).userSelect,
                    reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches,
                    theme: document.documentElement.getAttribute('data-theme'),
                })""")
                assert values["scrollWidth"] <= width and values["outputWidth"] > 0
                assert values["reducedMotion"] and values["selectable"] != "none"
                assert values["theme"] == theme
                geometry.append({"theme": theme, "width": width, "height": height, **values})
                context.close()
        outcomes["longPathGeometry"] = geometry
        browser.close()
    assert not network and not page_errors, (network, page_errors)
    assert not product_build_errors(REPO)
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == manifest_hash
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == runner_hash
    report = {
        "status": "PASS",
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
        "productManifestSha256": manifest_hash,
        "runnerSha256": runner_hash,
        "outcomes": outcomes,
        "networkRequests": network,
        "pageErrors": page_errors,
        "scope": (
            "Actual built React renderer and pinned Chromium; explicit native/Core doubles. "
            "Not Windows dialog, real Core, sign-in or W1 qualification."
        ),
    }
    publish_report(report_path, report)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
