"""Built renderer/client/Core commit journey; native host is an explicit double."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

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

from tests.service import test_import_review_api as api_fixture  # noqa: E402


class ImportCommitInteractionTests(unittest.TestCase):
    def test_commit_lost_reply_manifest_replay_and_navigation_in_both_themes(self):
        self.assertEqual([], product_build_errors(REPO))
        api = api_fixture.ImportReviewApiTests(methodName="runTest")
        with patch("research_observatory_core.import_preview_service.ImportPreviewService.start"):
            api.setUp()
        self.addCleanup(api.doCleanups)
        f = api.fixture
        api.post("begin-review")
        f.service.schedule_summary(f.root, api.preview, revision=1)
        f.service.run_pending()
        f.service.detach(f.root)
        f.projects.close(root=f.root, trace_id="1" * 32)
        calls = []
        lose_reply = True

        def native(command, args):
            nonlocal lose_reply
            self.assertEqual("core_api_request", command)
            request = args["request"]
            calls.append(request["path"])
            headers = {"Content-Type": "application/json"}
            if request["ifMatch"] is not None:
                headers["If-Match"] = request["ifMatch"]
            if request["idempotencyKey"] is not None:
                headers["Idempotency-Key"] = request["idempotencyKey"]
            result = api.client.request(request["method"], request["path"], content=request["body"], headers=headers)
            if request["path"] == "/projects/imports/commit/start" and lose_reply:
                lose_reply = False
                raise RuntimeError("synthetic-lost-reply-after-admission")
            return {
                "status": result.status_code,
                "contentType": result.headers["content-type"].split(";")[0],
                "traceId": result.headers["x-trace-id"],
                "etag": result.headers.get("etag"),
                "body": result.text,
            }

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
          window.__TAURI_INTERNALS__.invoke = (command, args) => command === 'core_api_request'
            ? window.__import_commit_native(command, args) : prior(command, args);
        })();"""
        )
        with self.subTest(boundary="built-renderer-and-core"):
            playwright = self.enterContext(sync_playwright())
            browser = playwright.chromium.launch(headless=True)
            self.addCleanup(browser.close)
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
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
            page.set_default_timeout(7000)
            page.expose_function("__import_commit_native", native)
            page.add_init_script(script)
            page.goto("http://tauri.localhost/index.html", wait_until="load")
            page.wait_for_function("document.body.dataset.applicationReady === 'true'")
            menu = page.locator("[data-all-tools]")

            def navigate(name):
                if menu.get_attribute("open") is None:
                    menu.locator("summary").click()
                menu.get_by_role("button", name=name, exact=True).click()

            navigate("Local projects")
            choose_fixture_directory(page, "project-root", f.root)
            page.get_by_role("button", name="Open project", exact=True).click()
            page.get_by_text("Exclusive local session open", exact=True).wait_for()
            navigate("Ingestion & Reconciliation")
            page.locator(".import-batches").get_by_role("button").first.click()
            commit = page.get_by_label("Import commit", exact=True)
            commit.get_by_text("No commit job reported", exact=True).wait_for()
            self.assertFalse(any(path.endswith("/commit/start") for path in calls))
            for theme in ("light", "dark"):
                self.assertEqual(theme, page.locator("html").get_attribute("data-theme"))
                review = commit.get_by_role("button", name="Review commit…", exact=True)
                review.click()
                page.wait_for_function("document.activeElement?.textContent === 'Confirm draft 1'")
                page.keyboard.press("Escape")
                page.wait_for_function("document.activeElement?.textContent === 'Review commit…'")
                review.click()
                commit.get_by_role("button", name="Commit this draft", exact=True).click()
                if theme == "light":
                    commit.get_by_text("Commit status needs attention", exact=True).wait_for()
                    commit.get_by_role("button", name="Refresh commit status", exact=True).click()
                    commit.get_by_text("Commit runnable", exact=True).wait_for()
                    f.service.run_pending()
                    commit.get_by_role("button", name="Refresh commit status", exact=True).click()
                commit.get_by_text("Committed — awaiting reconciliation", exact=True).wait_for()
                commit.get_by_role("button", name="Open import manifest", exact=True).click()
                manifest = page.get_by_label("Import manifest", exact=True)
                manifest.get_by_role("table").wait_for()
                self.assertIn("1 new source records; 0 reused source records", manifest.inner_text())
                self.assertIn("Excluded", manifest.inner_text())
                self.assertIn("Included", manifest.inner_text())
                retained = f.service.latest_commit_status(f.root, api.preview)[1]
                self.assertEqual(1, retained.created_count)
                self.assertEqual(2, retained.record_count)
                # Navigation re-discovers the accepted result, not a renderer-only success notice.
                navigate("Local projects")
                navigate("Ingestion & Reconciliation")
                page.locator(".import-batches").get_by_role("button").first.click()
                commit.get_by_text("Committed — awaiting reconciliation", exact=True).wait_for()
                if theme == "light":
                    page.locator("[data-theme-toggle]").click()
            self.assertEqual(2, calls.count("/projects/imports/commit/start"))
            page.wait_for_function("!document.querySelector('[aria-busy=\"true\"]')")
            page.goto("about:blank")
