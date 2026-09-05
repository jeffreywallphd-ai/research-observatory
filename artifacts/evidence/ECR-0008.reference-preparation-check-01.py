"""Read-only proposal checks and isolated browser previews, never baseline approval.

Generated observations stay under artifacts/tmp. Neither the active reference nor
product, workflow state, approved baseline, or researcher directories are written.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import ui_conformance as ui  # noqa: E402
import ui_reference_check as integrity  # noqa: E402

CANDIDATE = ROOT / "planning/enabler-change-requests/ECR-0008.reference-1.6"
ACTIVE = ROOT / "design/ui-reference"
OUT = ROOT / "artifacts/tmp/ecr8-reference16-preview-01"
SOURCES = ("WORKFLOW_CATALOG.json", "CAPABILITY_COVERAGE.json", "SITE_MANIFEST.json")
PAGES = ("projects.html", "new-project.html", "style-guide.html")


def semantic_payload(text: str) -> str:
    """Only the two exact root metadata values may change; retain all other bytes."""
    data = json.loads(text)
    assert data["reference_id"] in {"RO-UI-ACADEMIC-MINIMAL-1.5", "RO-UI-ACADEMIC-MINIMAL-1.6"}
    assert data["version"] in {"1.5", "1.6"}
    # A whole-document textual comparison also retains ordering and formatting.
    # Replace each metadata field once, where the authenticated source places it.
    return text.replace('"reference_id": "RO-UI-ACADEMIC-MINIMAL-1.6"',
                        '"reference_id": "RO-UI-ACADEMIC-MINIMAL-1.5"', 1).replace(
                            '"version": "1.6"', '"version": "1.5"', 1)


def main() -> int:
    if CANDIDATE.resolve() != CANDIDATE or OUT.parent.resolve() != OUT.parent:
        raise ValueError("Redirected candidate or output parent")
    if OUT.exists() and (OUT.is_symlink() or OUT.is_junction()):
        raise ValueError("Redirected output")
    OUT.mkdir(exist_ok=True)
    report: dict = {
        "documentType": "inert-reference-preparation-observation",
        "approval": False,
        "applicationQualification": False,
        "candidateRoot": CANDIDATE.relative_to(ROOT).as_posix(),
        "errors": [],
        "semantics": [],
        "screenshots": [],
        "interactionCases": [],
        "limitations": [
            "Static reference buttons demonstrate intent only, not native/Core execution.",
            "The inherited reference shell has a 1100px minimum width. These previews do not qualify the product at 200% scaling.",
            "No approved baseline is written. Fresh baseline generation and actual product/native qualification require later approved execution.",
        ],
    }
    for name in SOURCES:
        original = (ACTIVE / name).read_text(encoding="utf-8")
        proposed = (CANDIDATE / name).read_text(encoding="utf-8")
        same = semantic_payload(proposed) == original
        report["semantics"].append({"path": name, "onlyRootIdentityAndVersionChanged": same})
        if not same:
            report["errors"].append(f"Unexpected semantic/source change: {name}")
    for name in ("assets/tokens.css", "assets/app.js", "assets/print.css"):
        if integrity.sha256(ACTIVE / name) != integrity.sha256(CANDIDATE / name):
            report["errors"].append(f"Unexpected shared source change: {name}")
    candidate_check = integrity.validate(CANDIDATE)
    expected_gates = ["reference is not approved: status='proposed'", "manifest is not approved: status='proposed'"]
    if candidate_check["errors"] != expected_gates:
        report["errors"].extend(candidate_check["errors"])
    report["integrity"] = candidate_check
    config = json.loads((ROOT / "verification/extensions/desktop-ui.json").read_text())
    config.update(mode="inert-proposal-preview", referenceId="RO-UI-ACADEMIC-MINIMAL-1.6",
                  referencePackageSha256=candidate_check["reference_package_sha256"])
    config["normativeSources"] = {key: value.replace("design/ui-reference", CANDIDATE.relative_to(ROOT).as_posix())
                                  for key, value in config["normativeSources"].items()}
    site = json.loads((CANDIDATE / "SITE_MANIFEST.json").read_text())
    workflows = json.loads((CANDIDATE / "WORKFLOW_CATALOG.json").read_text())["workflows"]
    contracts = json.loads((CANDIDATE / "CAPABILITY_COVERAGE.json").read_text())["page_contracts"]
    context = ui.Context(ROOT, config, CANDIDATE, CANDIDATE, site, workflows, contracts,
                         [item["file"] for item in site["pages"]])
    route_check = ui.check_routes(context)
    report["routeStructure"] = route_check
    report["errors"].extend(route_check["errors"])
    observations, visual_errors = ui.render_visuals(context)
    report["proposedVisualObservations"] = observations
    report["errors"].extend(visual_errors)
    report["runtime"] = {"platform": platform.platform(), "playwright": importlib.metadata.version("playwright")}
    browser_runtime, browser = ui.open_browser(context)
    report["runtime"]["browser"] = browser.version
    viewports = [{"width": 1440, "height": 900}, {"width": 1280, "height": 720}, {"width": 720, "height": 450}]
    try:
        for viewport in viewports:
            for theme in ("light", "dark"):
                page = ui.new_page(browser, context, viewport, theme)
                try:
                    for name in PAGES:
                        ui.set_page(page, context, name, theme)
                        page.evaluate("window.scrollTo(0, 0)")
                        if name == "style-guide.html":
                            page.locator("#local-folders").scroll_into_view_if_needed()
                        capture = OUT / f"{Path(name).stem}-{viewport['width']}x{viewport['height']}-{theme}.png"
                        payload = page.screenshot(path=str(capture), full_page=False, animations="disabled", caret="hide", scale="device")
                        report["screenshots"].append({"page": name, "theme": theme, "viewport": viewport,
                                                      "path": capture.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(payload).hexdigest()})
                        fields = page.locator('[role="group"][aria-labelledby]:has(.directory-location)')
                        assert fields.count() == 1, f"Missing or duplicated shared folder control: {name}"
                        field = fields.first
                        before = field.locator("output").inner_text()
                        button = field.locator("button")
                        button.focus()
                        assert button.evaluate("node => node === document.activeElement"), "Folder button cannot receive focus"
                        style = button.evaluate("node => ({shadow:getComputedStyle(node).boxShadow, outline:getComputedStyle(node).outlineStyle})")
                        page.keyboard.press("Enter")
                        assert field.locator("output").inner_text() == before, "Mock selection changed a real location"
                        assert not field.locator("input, textarea, select").count(), "Folder text entry was reintroduced"
                        assert page.locator('input[type="file"]').count() == 0, "Browser directory enumeration is forbidden"
                        # Stress only the output text in memory; the proposal file stays untouched.
                        width_before = page.evaluate("document.documentElement.scrollWidth")
                        field.locator("output").evaluate("node => node.textContent = 'C:/Research/研究 ' + 'long-directory-'.repeat(35)")
                        geometry = field.locator("output").evaluate("node => ({scroll:node.scrollWidth, client:node.clientWidth, wrap:getComputedStyle(node).overflowWrap, select:getComputedStyle(node).userSelect})")
                        assert geometry["scroll"] <= geometry["client"] + 1, "Long path escapes the shared output"
                        assert page.evaluate("document.documentElement.scrollWidth") == width_before, "Long path adds horizontal page overflow"
                        assert geometry["wrap"] == "anywhere" and geometry["select"] == "text"
                        summaries = page.locator("details > summary").filter(has_text="separate reference examples")
                        assert summaries.count() == 2
                        for summary in summaries.all():
                            summary.focus()
                            page.keyboard.press("Enter")
                            assert summary.evaluate("node => node.parentElement.open"), "State examples are not keyboard accessible"
                        if viewport["width"] == 1440:
                            states_capture = OUT / f"{Path(name).stem}-states-{theme}.png"
                            summaries.first.scroll_into_view_if_needed()
                            states_payload = page.screenshot(path=str(states_capture), full_page=False, animations="disabled", caret="hide", scale="device")
                            report["screenshots"].append({"page": name, "theme": theme, "viewport": viewport,
                                                          "state": "examples-expanded-with-in-memory-long-path-stress",
                                                          "path": states_capture.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(states_payload).hexdigest()})
                        report["interactionCases"].append({"page": name, "theme": theme, "viewport": viewport,
                                                           "mockClickPreservedSelection": True, "pathEntryAbsent": True,
                                                           "longPath": geometry, "pageWidthBeforeLongPath": width_before,
                                                           "visibleFocusStyle": style, "keyboardDisclosures": 2})
                finally:
                    page.context.close()
    finally:
        browser.close()
        browser_runtime.stop()
    report["okForPreparation"] = not report["errors"]
    (OUT / "observations.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"okForPreparation": report["okForPreparation"], "errors": report["errors"],
                      "visualObservations": len(observations), "screenshots": len(report["screenshots"]),
                      "interactionCases": len(report["interactionCases"]), "report": str(OUT / "observations.json")}, indent=2))
    return 0 if report["okForPreparation"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
