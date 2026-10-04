"""Characterize the one challenged explicit-label input in pinned Chromium."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo / "tools"))
from ui_conformance import accessible_name, load_context, new_page, open_browser, set_page, soup  # noqa: E402

candidate = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
context = load_context(repo)
if platform.system() != "Windows" or platform.machine().lower() not in {"amd64", "x86_64"}:
    raise ValueError("Windows x64 required")
if importlib.metadata.version("playwright") != context.config["visual"]["playwrightVersion"]:
    raise ValueError("pinned Playwright required")
name = "ingestion-reconciliation.html"
document = soup(context.target / name)
control = document.select_one("#attachment-file")
static_name = accessible_name(control)
expected = "Local full-text file"
observations = []
playwright, browser = open_browser(context)
try:
    if browser.version != context.config["visual"]["browserVersion"]:
        raise ValueError("pinned Chromium required")
    page = new_page(browser, context)
    try:
        set_page(page, context, name)
        page.locator("#attachment-file").focus()
        cdp = page.context.new_cdp_session(page)

        def ax_name() -> dict:
            root = cdp.send("DOM.getDocument")["root"]["nodeId"]
            node = cdp.send("DOM.querySelector", {"nodeId": root, "selector": "#attachment-file"})["nodeId"]
            tree = cdp.send("Accessibility.getPartialAXTree", {"nodeId": node, "fetchRelatives": False})["nodes"]
            if len(tree) != 1:
                raise ValueError("ambiguous accessibility node")
            item = tree[0]
            return {
                "ignored": item["ignored"],
                "role": item.get("role", {}).get("value"),
                "name": item.get("name", {}).get("value"),
                "nameSources": item.get("name", {}).get("sources"),
            }

        positive = ax_name()
        label_count = page.get_by_label(expected, exact=True).count()
        if positive["ignored"] or positive["name"] != expected or label_count != 1:
            raise ValueError("explicit approved label was not resolved by Chromium")
        observations.append(
            {"case": "unchanged approved explicit for/id label", "ax": positive, "labelLocatorCount": label_count}
        )
        page.locator('label[for="attachment-file"]').evaluate("node => node.remove()")
        negative = ax_name()
        negative_count = page.get_by_label(expected, exact=True).count()
        if negative["name"] == expected or negative_count:
            raise ValueError("removing the associated label did not fail the name criterion")
        observations.append(
            {"case": "in-memory label removal only", "ax": negative, "labelLocatorCount": negative_count}
        )
    finally:
        page.context.close()
finally:
    browser.close()
    playwright.stop()
if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip() != candidate:
    raise ValueError("HEAD changed during characterization")
report = {
    "ok": True,
    "candidateCommit": candidate,
    "page": name,
    "staticCheckerName": static_name,
    "referenceSourceSha256": hashlib.sha256((context.reference / name).read_bytes()).hexdigest(),
    "builtFixtureSha256": hashlib.sha256((context.target / name).read_bytes()).hexdigest(),
    "observations": observations,
    "scope": "single challenged reference-fixture input; no native or Core proof; no checker waiver or source edit",
}
destination = repo / "artifacts/tmp/W2.A03.T02.file-input-accessibility-aab29ed2.json"
destination.write_bytes((json.dumps(report, indent=2, sort_keys=True) + "\n").encode())
print(json.dumps(report, sort_keys=True))
