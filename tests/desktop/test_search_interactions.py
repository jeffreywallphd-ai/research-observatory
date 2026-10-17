"""Production React/generated search client with an explicit controlled Core port.

The real protected Core and Rust principal are separate checks. This check serves
the actual bundled modules locally and exercises shell/Reader return continuity.
It does not substitute the historical shared desktop checker verdict.
"""

import mimetypes
import unittest
from contextlib import ExitStack
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from tests.desktop.test_model_center_interactions import ModelCenterInteractionTests, choose_fixture_directory

ROOT = Path(__file__).resolve().parents[2]
PRODUCT = ROOT / "apps/desktop/product-dist"
PROJECT = "11111111-1111-4111-8111-111111111111"


class SearchInteractionTests(unittest.TestCase):
    def fixture(self):
        base = ModelCenterInteractionTests().supporting_workflow_fixture()
        return base + (ROOT / "tests/desktop/fixtures/search-core-port.mjs").read_text("utf-8")

    def page(self, context):
        def serve(route):
            url = route.request.url
            if not url.startswith("http://tauri.localhost/"):
                route.abort()
                return
            relative = url.removeprefix("http://tauri.localhost/") or "index.html"
            candidate = (PRODUCT / relative).resolve()
            try:
                candidate.relative_to(PRODUCT.resolve())
            except ValueError:
                route.abort()
                return
            if not candidate.is_file():
                route.abort()
                return
            route.fulfill(
                path=str(candidate),
                content_type="text/javascript"
                if candidate.suffix == ".js"
                else mimetypes.guess_type(candidate)[0] or "application/octet-stream",
            )

        context.route("**/*", serve)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.add_init_script(self.fixture())
        page.goto("http://tauri.localhost/index.html", wait_until="load")
        page.wait_for_function("document.body.dataset.applicationReady === 'true'")
        helper = ModelCenterInteractionTests()
        helper.open_supporting_tool(page, "Local projects")
        choose_fixture_directory(page, "project-root", "C:/Research/study-one")
        page.get_by_role("button", name="Open project", exact=True).click()
        page.get_by_text("Exclusive local session open", exact=True).wait_for()
        page.locator("[data-workflow-nav]").wait_for()
        helper.open_supporting_tool(page, "Search Studio")
        page.locator("[data-search-workspace]").wait_for()
        return page, errors

    def draft(self, page):
        page.get_by_label("Query draft", exact=True).fill("title:café")
        page.get_by_label("Year from", exact=True).fill("2020")
        page.get_by_label("Year to", exact=True).fill("2026")

    def test_exact_page_source_return_keyboard_denial_and_both_themes(self):
        with sync_playwright() as runtime, ExitStack() as cleanup:
            browser = runtime.chromium.launch(headless=True)
            cleanup.callback(browser.close)
            context = browser.new_context(viewport={"width": 1280, "height": 900}, reduced_motion="reduce")
            cleanup.callback(context.close)
            page, errors = self.page(context)
            self.draft(page)
            page.get_by_role("button", name="Validate / preview draft", exact=True).click()
            expect(page.get_by_role("heading", name="Normalized query preview")).to_be_visible()
            self.assertFalse(
                any(value["path"].endswith("/run") for value in page.evaluate("window.__SEARCH_TEST__.calls"))
            )
            page.get_by_role("button", name="Run search", exact=True).click()
            page.get_by_role("button", name="Inspect source for rank 50", exact=True).wait_for()
            page.get_by_role("button", name="Next results", exact=True).click()
            source = page.get_by_role("button", name="Inspect source for rank 51", exact=True)
            source.wait_for()
            self.assertEqual("<script>", page.locator("[data-search-workspace] mark").inner_text())
            self.assertEqual(0, page.locator("[data-search-workspace] script").count())
            explain = page.get_by_role("button", name="Explain rank 51", exact=True)
            explain.focus()
            page.keyboard.press("Enter")
            expect(page.get_by_role("heading", name="Ranking explanation", exact=True)).to_be_focused()
            page.keyboard.press("Escape")
            expect(explain).to_be_focused()
            source.focus()
            page.keyboard.press("Enter")
            page.get_by_role("button", name="Return to Search Studio", exact=True).click()
            expect(source).to_be_focused()
            expect(page.get_by_label("Query draft", exact=True)).to_have_value("title:café")
            expect(page.get_by_label("Year from", exact=True)).to_have_value("2020")
            self.assertEqual(0, page.get_by_role("button", name="Inspect source for rank 1", exact=True).count())
            for theme in ("light", "dark"):
                page.evaluate("theme=>document.documentElement.dataset.theme=theme", theme)
                page.set_viewport_size({"width": 420, "height": 900})
                self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 420)
                self.assertNotEqual(
                    "rgba(0, 0, 0, 0)",
                    page.locator("[data-search-workspace] mark").evaluate(
                        "node=>getComputedStyle(node).backgroundColor"
                    ),
                )
            page.evaluate("window.__SEARCH_TEST__.deny=true")
            page.get_by_role("button", name="Recheck current access", exact=True).click()
            expect(page.get_by_text("Search inaccessible", exact=True)).to_be_visible()
            self.assertEqual(0, page.locator("[data-search-workspace] mark").count())
            expect(page.get_by_role("heading", name="Search Studio", exact=True)).to_be_focused()
            self.assertNotIn("Synthetic café", page.evaluate("JSON.stringify(localStorage)"))
            self.assertEqual([], errors)

    def test_lost_acknowledgement_and_failed_poll_have_same_command_and_visible_recovery(self):
        with sync_playwright() as runtime, ExitStack() as cleanup:
            browser = runtime.chromium.launch(headless=True)
            cleanup.callback(browser.close)
            context = browser.new_context()
            cleanup.callback(context.close)
            page, errors = self.page(context)
            self.draft(page)
            page.evaluate("Object.assign(window.__SEARCH_TEST__,{loseAck:true,running:true,pollFailure:true})")
            page.get_by_role("button", name="Run search", exact=True).click()
            page.get_by_role("button", name="Retry same search command", exact=True).click()
            expect(page.get_by_text("Search inaccessible", exact=True)).to_be_visible()
            runs = page.evaluate("window.__SEARCH_TEST__.calls.filter(value=>value.path.endsWith('/run'))")
            self.assertEqual(2, len(runs))
            self.assertEqual(runs[0], runs[1])
            expect(page.get_by_role("button", name="Run search", exact=True)).to_be_disabled()
            page.evaluate("window.__SEARCH_TEST__.running=false")
            page.get_by_role("button", name="Recheck search status", exact=True).click()
            page.get_by_role("button", name="Inspect source for rank 50", exact=True).wait_for()
            self.assertEqual([], errors)

    def test_late_anchor_reply_cannot_override_navigation_or_locked_context(self):
        with sync_playwright() as runtime, ExitStack() as cleanup:
            browser = runtime.chromium.launch(headless=True)
            cleanup.callback(browser.close)
            context = browser.new_context()
            cleanup.callback(context.close)
            page, errors = self.page(context)
            self.draft(page)
            page.evaluate("window.__SEARCH_TEST__.holdAnchor=true")
            page.get_by_role("button", name="Run search", exact=True).click()
            page.get_by_role("button", name="Inspect source for rank 50", exact=True).click()
            page.wait_for_function("window.__SEARCH_TEST__.releaseAnchor!==null")
            ModelCenterInteractionTests().open_supporting_tool(page, "Project home")
            page.evaluate("window.__SEARCH_TEST__.releaseAnchor()")
            self.assertEqual(0, page.locator("[data-search-workspace]").count())
            self.assertEqual(0, page.get_by_role("button", name="Return to Search Studio", exact=True).count())
            ModelCenterInteractionTests().open_supporting_tool(page, "Search Studio")
            page.get_by_role("button", name="Inspect source for rank 50", exact=True).wait_for()
            page.evaluate("window.__SEARCH_TEST__.locked=true")
            page.locator("[data-application-locked]").wait_for(timeout=6000)
            self.assertNotIn("title:café", page.inner_text("body"))
            self.assertNotIn("Synthetic café", page.inner_text("body"))
            self.assertNotIn("title:café", page.evaluate("JSON.stringify(localStorage)"))
            self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
