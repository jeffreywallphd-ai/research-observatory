"""Built renderer + generated client + authenticated Core/project composition.

Native chooser/host are explicit doubles. The repository, encrypted object port,
parser, worker, draft revisions and review API are real; the database uses the
existing explicit plaintext test fixture. Not Windows dialog/DPAPI qualification.
"""

from __future__ import annotations

import base64
import hashlib
import sys
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "services/core-api/src"))

from desktop_app_check import (  # noqa: E402
    DIRECTORY_PICKER_FIXTURE,
    choose_fixture_directory,
    core_workflow_catalog_json,
    inline_product_index,
    product_build_errors,
)

from tests.service import test_import_intake_api as intake_api_fixture  # noqa: E402


class ImportInteractionTests(unittest.TestCase):
    def test_real_review_mapping_group_correction_and_exclusion_in_both_themes(self):
        self.assertEqual([], product_build_errors(REPO))
        api = intake_api_fixture.ImportIntakeApiTests(methodName="runTest")
        api.setUp()
        self.addCleanup(api.doCleanups)
        fixture = api.fixture
        fixture.service.detach(fixture.root)
        fixture.projects.close(root=fixture.root, trace_id="1" * 32)
        raw = (
            "title;title;doi\n"
            + "".join(f"Synthetic {n};Alternative {n};10.99999/EXAMPLE{n // 2}\n" for n in range(55))
        ).encode()
        selected_previews = []
        calls = []

        def native(command, args):
            if command == "core_api_request":
                request = args["request"]
                calls.append(request["path"])
                headers = {"Content-Type": "application/json"}
                if request["ifMatch"] is not None:
                    headers["If-Match"] = request["ifMatch"]
                if request["idempotencyKey"] is not None:
                    headers["Idempotency-Key"] = request["idempotencyKey"]
                response = api.client.request(
                    request["method"], request["path"], content=request["body"], headers=headers
                )
                return {
                    "status": response.status_code,
                    "contentType": response.headers["content-type"].split(";")[0],
                    "traceId": response.headers["x-trace-id"],
                    "etag": response.headers.get("etag"),
                    "body": response.text,
                }
            if command == "import_selected_file":
                request = args["request"]
                self.assertEqual(fixture.root, request["root"])
                self.assertEqual(fixture.project_id, request["projectId"])
                self.assertNotIn("sourcePath", request)
                self.assertEqual(";", request["delimiter"])
                context = api.session()
                created = api.create(
                    context,
                    sourceName="synthetic-preview.csv",
                    formatName=request["formatName"],
                    encoding=request["encoding"],
                    delimiter=request["delimiter"],
                    rights=request["rights"],
                )
                self.assertEqual(200, created.status_code)
                address = {**context, "previewId": created.json()["previewId"]}
                selected_previews.append(address["previewId"])
                self.assertEqual(
                    200, api.post("chunk", address, ordinal=1, data=base64.b64encode(raw).decode()).status_code
                )
                self.assertEqual(
                    200,
                    api.post(
                        "seal", address, sourceSha256=hashlib.sha256(raw).hexdigest(), byteLength=len(raw), chunkCount=1
                    ).status_code,
                )
                scheduled = api.post("schedule", address)
                self.assertEqual(200, scheduled.status_code)
                return {
                    "status": "prepared",
                    "sourceName": "synthetic-preview.csv",
                    "preview": api.post("status", address).json(),
                }
            if command == "cancel_import_file":
                return None
            if command == "save_import_report":
                request = args["request"]
                self.assertEqual({"root", "projectId", "previewId", "revision", "operationId"}, set(request))
                address = {**api.session(), "previewId": request["previewId"]}
                after = 0
                fragments = []
                while True:
                    result = api.post("report", address, revision=request["revision"], after=after, limit=25)
                    self.assertEqual(200, result.status_code)
                    item = result.json()
                    fragments.append(item["csv"])
                    after = item["nextAfter"]
                    if item["complete"]:
                        break
                final = api.post("report", address, revision=request["revision"], after=after, limit=25)
                self.assertEqual(200, final.status_code)
                self.assertEqual("", final.json()["csv"])
                report = "".join(fragments)
                self.assertEqual(56, after)
                self.assertIn("excluded", report)
                self.assertNotIn("Synthetic", report)
                self.assertNotIn("Researcher correction", report)
                self.assertEqual(1, report.count("ordinal,line_start"))
                return {
                    "status": "saved",
                    "filename": f"import-diagnostics-{request['operationId']}.csv",
                    "byteLength": len(report.encode()),
                }
            raise AssertionError("Unexpected test-host command")

        script = (
            (REPO / "tests/desktop/fixtures/task_center_interactions.js")
            .read_text("utf-8")
            .replace("__WORKFLOW_CATALOG__", core_workflow_catalog_json(REPO))
        )
        script += (
            DIRECTORY_PICKER_FIXTURE
            + """;
        (() => {
          const prior = window.__TAURI_INTERNALS__.invoke;
          window.__TAURI_INTERNALS__.invoke = (command, args) =>
            ['core_api_request', 'import_selected_file', 'cancel_import_file', 'save_import_report'].includes(command)
              ? window.__import_test_native(command, args) : prior(command, args);
        })();"""
        )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
            try:
                document = inline_product_index(REPO)
                context.route(
                    "**/*",
                    lambda route: (
                        route.fulfill(status=200, content_type="text/html", body=document)
                        if route.request.url == "http://tauri.localhost/index.html"
                        else route.abort()
                    ),
                )
                page = context.new_page()
                page.set_default_timeout(5000)
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.expose_function("__import_test_native", native)
                page.add_init_script(script)
                page.goto("http://tauri.localhost/index.html", wait_until="load")
                page.wait_for_function("document.body.dataset.applicationReady === 'true'")
                page.evaluate("""() => {
                  window.__importAnnouncements = [];
                  const live = document.querySelector('[data-live-region]');
                  new MutationObserver(() => {
                    if (live.textContent) window.__importAnnouncements.push(live.textContent);
                  }).observe(live, { childList: true, subtree: true, characterData: true });
                }""")
                menu = page.locator("[data-all-tools]")
                menu.locator("summary").click()
                menu.get_by_role("button", name="Local projects", exact=True).click()
                choose_fixture_directory(page, "project-root", fixture.root)
                page.get_by_role("button", name="Open project", exact=True).click()
                page.get_by_text("Exclusive local session open", exact=True).wait_for(timeout=5000)
                if menu.get_attribute("open") is None:
                    menu.locator("summary").click()
                menu.get_by_role("button", name="Ingestion & Reconciliation", exact=True).click()
                workspace = page.locator("[data-import-workspace]")
                workspace.wait_for()
                choose = workspace.get_by_role("button", name="Choose reference file…", exact=True)
                self.assertTrue(choose.is_disabled())
                page.get_by_label("Reference format", exact=True).select_option("csv")
                page.get_by_label("CSV separator", exact=True).select_option("\t")
                self.assertEqual("\t", page.get_by_label("CSV separator", exact=True).input_value())
                page.get_by_label("Reference format", exact=True).select_option("ris")
                self.assertEqual(0, page.get_by_label("CSV separator", exact=True).count())
                page.get_by_label("Reference format", exact=True).select_option("csv")
                self.assertEqual(",", page.get_by_label("CSV separator", exact=True).input_value())
                page.get_by_label("CSV separator", exact=True).select_option(";")
                page.get_by_label("I confirm I may store and inspect this file locally.", exact=True).check()
                choose.focus()
                page.keyboard.press("Enter")
                batch = workspace.locator(".import-batches").get_by_role("button")
                batch.get_by_text("Parsing: runnable", exact=True).wait_for()
                fixture.service.run_pending()
                page.get_by_role("button", name="Apply column mapping", exact=True).wait_for(timeout=10000)
                batch.get_by_text("Ready for review", exact=True).wait_for()
                page.locator("[data-live-region]").get_by_text(
                    "Import preview: Ready for review.", exact=True
                ).wait_for()
                self.assertEqual("title", page.locator("#import-column-0").input_value())
                self.assertEqual("title", page.locator("#import-column-1").input_value())
                self.assertEqual("doi", page.locator("#import-column-2").input_value())
                for theme in ("light", "dark"):
                    self.assertEqual(theme, page.locator("html").get_attribute("data-theme"))
                    workspace.get_by_text("CSV separator: Semicolon.", exact=False).wait_for()
                    page.locator("#import-column-0").select_option("title")
                    page.locator("#import-column-1").select_option("")
                    page.locator("#import-column-2").select_option("doi")
                    page.get_by_role("button", name="Next records", exact=True).click()
                    page.get_by_role("button", name="Previous records", exact=True).click()
                    page.get_by_label("Select record 2", exact=True).wait_for()
                    self.assertEqual("", page.locator("#import-column-1").input_value())
                    apply = page.get_by_role("button", name="Apply column mapping", exact=True)
                    apply.focus()
                    page.keyboard.press("Enter")
                    page.wait_for_function(
                        "document.querySelector('[aria-label=\"Selected import preview\"]')"
                        "?.getAttribute('aria-busy') === 'false'"
                    )
                    summary_panel = page.get_by_label("Import summary and duplicate candidates", exact=True)
                    summary_panel.get_by_text("Not calculated", exact=True).wait_for()
                    calculate = summary_panel.get_by_role("button", name="Calculate preview summary", exact=True)
                    calculate.focus()
                    page.keyboard.press("Enter")
                    summary_panel.get_by_role("button", name="Cancel summary calculation", exact=True).wait_for()
                    fixture.service.run_pending()
                    summary_panel.get_by_role("button", name="Refresh summary status", exact=True).click()
                    summary_panel.get_by_text("Complete for this draft", exact=True).wait_for()
                    page.locator("[data-live-region]").get_by_text(
                        "Preview summary: Complete for this draft.", exact=True
                    ).wait_for()
                    announcements = page.evaluate("window.__importAnnouncements.length")
                    summary_panel.get_by_role("button", name="Refresh summary status", exact=True).click()
                    page.wait_for_function(
                        "document.querySelector('[aria-label=\"Import summary and duplicate candidates\"]')"
                        "?.getAttribute('aria-busy') === 'false'"
                    )
                    self.assertEqual(announcements, page.evaluate("window.__importAnnouncements.length"))
                    summary_panel.get_by_text("No works have been merged.", exact=False).wait_for()
                    summary_panel.get_by_role("button", name="Review group at row", exact=False).first.click()
                    summary_panel.get_by_role("button", name="Compare candidate row", exact=False).first.click()
                    page.get_by_role("region", name="raw fields", exact=True).wait_for()
                    summary_panel.get_by_role(
                        "button", name="Select this candidate page for editing", exact=True
                    ).click()
                    page.get_by_text("2 selected across pages (up to 100).", exact=False).wait_for()
                    page.get_by_role("button", name="Clear selection", exact=True).click()
                    page.get_by_label("Select record 2", exact=True).check()
                    page.get_by_role("button", name="Next records", exact=True).click()
                    page.get_by_label("Select record 27", exact=True).check()
                    page.get_by_label("Corrected value for selected records", exact=True).fill(
                        "Researcher correction " + theme
                    )
                    page.get_by_role("button", name="Apply correction to selected", exact=True).click()
                    row = page.get_by_role("button", name="Row 2: Researcher correction " + theme, exact=True)
                    row.wait_for()
                    row.click()
                    raw_fields = page.get_by_role("region", name="raw fields", exact=True)
                    raw_fields.get_by_text("Synthetic 0", exact=True).wait_for()
                    self.assertNotIn("Researcher correction", raw_fields.inner_text())
                    page.get_by_role("region", name="effective fields", exact=True).get_by_text(
                        "Researcher correction " + theme, exact=True
                    ).wait_for()
                    page.get_by_label("Select record 2", exact=True).check()
                    # The second theme reuses the prior excluded draft. Establish
                    # an explicit included state before testing exclusion + undo.
                    page.get_by_role("button", name="Include selected", exact=True).click()
                    page.wait_for_function(
                        "document.querySelector('[aria-label=\"Selected import preview\"]')"
                        "?.getAttribute('aria-busy') === 'false'"
                    )
                    preview = selected_previews[0]
                    before_exclusion = api.client.post(
                        "/projects/imports/review", json={"root": fixture.root, "previewId": preview}
                    ).json()
                    included_row = api.client.post(
                        "/projects/imports/records",
                        json={
                            "root": fixture.root,
                            "previewId": preview,
                            "revision": before_exclusion["revision"],
                            "after": 1,
                            "limit": 1,
                        },
                    ).json()["records"][0]
                    self.assertTrue(included_row["included"], theme)
                    page.get_by_label("Select record 2", exact=True).check()
                    page.get_by_role("button", name="Exclude selected", exact=True).click()
                    page.wait_for_function(
                        "document.querySelector('[aria-label=\"Selected import preview\"]')"
                        "?.getAttribute('aria-busy') === 'false'"
                    )
                    preview = selected_previews[0]
                    summary = api.client.post(
                        "/projects/imports/review", json={"root": fixture.root, "previewId": preview}
                    ).json()
                    records = api.client.post(
                        "/projects/imports/records",
                        json={
                            "root": fixture.root,
                            "previewId": preview,
                            "revision": summary["revision"],
                            "after": 1,
                            "limit": 1,
                        },
                    ).json()
                    self.assertFalse(records["records"][0]["included"])
                    self.assertEqual("Researcher correction " + theme, records["records"][0]["title"]["text"])
                    undo = page.get_by_role("button", name="Undo last draft change", exact=True)
                    undo.focus()
                    page.keyboard.press("Enter")
                    page.wait_for_function(
                        "document.activeElement?.textContent === 'Undo last draft change'"
                        " && !document.activeElement.disabled"
                    )
                    restored = api.client.post(
                        "/projects/imports/review", json={"root": fixture.root, "previewId": preview}
                    ).json()
                    self.assertEqual(summary["revision"] + 1, restored["revision"])
                    restored_row = api.client.post(
                        "/projects/imports/records",
                        json={
                            "root": fixture.root,
                            "previewId": preview,
                            "revision": restored["revision"],
                            "after": 1,
                            "limit": 1,
                        },
                    ).json()["records"][0]
                    self.assertTrue(restored_row["included"], theme)
                    self.assertEqual("Researcher correction " + theme, restored_row["title"]["text"])
                    page.get_by_label("Select record 2", exact=True).check()
                    page.get_by_role("button", name="Exclude selected", exact=True).click()
                    page.wait_for_function(
                        "document.querySelector('[aria-label=\"Selected import preview\"]')"
                        "?.getAttribute('aria-busy') === 'false'"
                    )
                    self.assertEqual(0, page.locator('input[type="file"]').count())
                    cancel_button = page.get_by_role("button", name="Cancel this preview…", exact=True)
                    cancel_button.focus()
                    page.keyboard.press("Enter")
                    page.keyboard.press("Tab")
                    self.assertEqual("Keep preview", page.evaluate("document.activeElement.textContent"))
                    page.keyboard.press("Enter")
                    self.assertTrue(cancel_button.evaluate("node => node === document.activeElement"))
                    page.keyboard.press("Enter")
                    page.keyboard.press("Tab")
                    page.keyboard.press("Escape")
                    self.assertEqual(0, page.get_by_role("button", name="Keep preview", exact=True).count())
                    self.assertTrue(cancel_button.evaluate("node => node === document.activeElement"))
                    download = page.get_by_role("button", name="Download diagnostic report…", exact=True)
                    download.focus()
                    page.keyboard.press("Enter")
                    workspace.get_by_text("in your selected folder.", exact=False).wait_for()
                    page.wait_for_function("document.activeElement?.textContent === 'Download diagnostic report…'")
                    page.locator("[data-theme-toggle]").click()
                # An older list reply must not overwrite a newer authoritative
                # cancellation, even when the user refreshed before cancelling.
                page.evaluate("""() => {
                  const prior = window.__TAURI_INTERNALS__.invoke;
                  window.__TAURI_INTERNALS__.invoke = async (command, args) => {
                    const result = await prior(command, args);
                    if (command === 'core_api_request' && args.request.path === '/projects/imports/list') {
                      return await new Promise(resolve => { window.__releaseImportList = () => resolve(result); });
                    }
                    return result;
                  };
                }""")
                page.get_by_role("button", name="Refresh batches", exact=True).click()
                page.wait_for_function("typeof window.__releaseImportList === 'function'")
                page.get_by_role("button", name="Cancel this preview…", exact=True).click()
                page.get_by_role("button", name="Confirm cancellation", exact=True).click()
                batch.get_by_text("cancelled", exact=True).wait_for()
                page.evaluate("window.__releaseImportList()")
                page.wait_for_function(
                    "!Array.from(document.querySelectorAll('button'))"
                    ".find(node => node.textContent === 'Refresh batches').disabled"
                )
                self.assertEqual("synthetic-preview.csvcancelled", batch.inner_text().replace("\n", ""))
                # Deliver an authentic Core response after navigation has unmounted
                # the private preview; it must not resurrect the old source UI.
                page.evaluate("""() => {
                  const prior = window.__TAURI_INTERNALS__.invoke;
                  window.__TAURI_INTERNALS__.invoke = async (command, args) => {
                    const result = await prior(command, args);
                    if (command === 'core_api_request' && args.request.path === '/projects/imports/status') {
                      return await new Promise(resolve => { window.__releaseImportStatus = () => resolve(result); });
                    }
                    return result;
                  };
                }""")
                page.get_by_role("button", name="Reload preview", exact=True).click()
                page.wait_for_function("typeof window.__releaseImportStatus === 'function'")
                if menu.get_attribute("open") is None:
                    menu.locator("summary").click()
                menu.get_by_role("button", name="Local projects", exact=True).click()
                page.evaluate("window.__releaseImportStatus()")
                page.get_by_role("heading", name="Local projects", exact=True).wait_for()
                self.assertEqual(0, page.locator("[data-import-workspace]").count())
                self.assertNotIn("synthetic-preview.csv", page.locator("main").inner_text())
                self.assertEqual([], errors)
                self.assertIn("/projects/imports/mapping", calls)
                self.assertIn("/projects/imports/edit", calls)
            finally:
                context.close()
                browser.close()


if __name__ == "__main__":
    unittest.main()
