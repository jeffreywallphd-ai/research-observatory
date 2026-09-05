"""Read-only built-product diagnostic for the user's W1 sidebar report.

The in-memory CSS experiment is explicitly not product implementation or
qualification. No real project or native service is accessed.
"""
import json
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo / "tools"))
from desktop_app_check import core_workflow_catalog_json, inline_product_index

document = inline_product_index(repo)
adapter = (repo / "tests/desktop/fixtures/task_center_interactions.js").read_text(
    encoding="utf-8"
).replace("__WORKFLOW_CATALOG__", core_workflow_catalog_json(repo))
result = {
    "documentType": "read-only-user-ux-diagnostic",
    "sourceCommit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip(),
    "actualProductChanged": False,
    "qualification": False,
    "cases": [],
}
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    for width, height in ((1440, 900), (1280, 720), (720, 450)):
        context = browser.new_context(viewport={"width": width, "height": height})
        context.add_init_script(adapter)
        page = context.new_page()
        page.route("**/*", lambda route: route.fulfill(body=document, content_type="text/html")
                   if route.request.url == "http://tauri.localhost/index.html" else route.abort())
        page.goto("http://tauri.localhost/index.html")
        page.locator(".application-shell[data-application-ready]").wait_for()
        tools = page.get_by_text("All tools", exact=True)
        if tools.count():
            tools.click()
        page.get_by_role("button", name="Local projects", exact=True).click()
        page.locator("#project-root").wait_for()
        page.wait_for_function("document.querySelector('#project-primary-use-case').options.length > 1")
        for phase in ("current-product", "in-memory-remove-height-cap"):
            if phase.startswith("in-memory"):
                page.add_style_tag(content=".sidebar { max-height: none; }")
            measurement = page.evaluate("""() => {
              const rect = selector => {
                const r = document.querySelector(selector).getBoundingClientRect();
                return {top: r.top + scrollY, bottom: r.bottom + scrollY, height: r.height};
              };
              const sidebar = rect('.sidebar');
              const footer = rect('.trust-footer');
              const shell = rect('.shell-body');
              return {sidebar, footer, shell,
                sidebarToFooterGap: footer.top - sidebar.bottom,
                documentWidth: document.documentElement.scrollWidth,
                viewportWidth: innerWidth,
                cap: getComputedStyle(document.querySelector('.sidebar')).maxHeight};
            }""")
            result["cases"].append({"viewport": [width, height], "phase": phase, **measurement})
        context.close()
    browser.close()
print(json.dumps(result, indent=2))
