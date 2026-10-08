"""Mounted actual renderer; explicit native-response double from real Core proof."""

import json
import os
import unittest
from contextlib import ExitStack
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]


class AnchorReaderInteractionTests(unittest.TestCase):
    def test_restart_selection_theme_reflow_unicode_fallback_denial_and_late_lock_clear(self):
        raw_path = os.environ.get("RO_ANCHOR_BROWSER_FIXTURE")
        bundle_root = os.environ.get("RO_ANCHOR_BROWSER_BUNDLE")
        if not raw_path or not bundle_root:
            self.skipTest("requires the owned Core native-composition fixture and built reader bundle")
        source = Path(raw_path).resolve()
        bundle = Path(bundle_root).resolve()
        for path in (source, bundle):
            path.relative_to((ROOT / "artifacts/tmp").resolve())
        fixture = json.loads(source.read_text("utf-8"))
        self.assertEqual("synthetic-anchor-from-actual-Core-native-composition", fixture["kind"])
        script = (bundle / "source-anchor-reader.js").read_text("utf-8")
        style = (bundle / "source-anchor-reader.css").read_text("utf-8")
        html = '<!doctype html><html><body><div id="root"></div></body></html>'
        with sync_playwright() as playwright, ExitStack() as cleanup:
            browser = playwright.chromium.launch(headless=True)
            cleanup.callback(browser.close)
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
            cleanup.callback(context.close)
            context.route("**/*", lambda route: route.fulfill(status=200, content_type="text/html", body=html))
            page = context.new_page()
            page.goto("http://127.0.0.1:49153/anchor-fixture")
            page.evaluate("fixture => { window.__ANCHOR_FIXTURE__ = fixture; }", fixture)
            page.add_style_tag(content=style)
            page.add_script_tag(content=script)
            open_anchor = page.get_by_role("button", name="Open saved anchor 1", exact=True)
            open_anchor.wait_for()
            open_anchor.focus()
            page.keyboard.press("Enter")
            mark = page.locator('mark[aria-label="Selected source passage"]')
            mark.wait_for()
            self.assertEqual("Second synthetic passage", mark.inner_text())
            self.assertIn("Structural/text fallback", page.inner_text("body"))
            self.assertIn(fixture["anchor"]["target"]["revisionId"], page.inner_text("body"))
            self.assertEqual("Source passage", page.locator(":focus").inner_text())
            for theme in ("light", "dark"):
                page.evaluate("theme => { document.documentElement.dataset.theme = theme; }", theme)
                page.get_by_label("Text size").select_option("200")
                self.assertEqual("Second synthetic passage", mark.inner_text())
                self.assertNotEqual("rgba(0, 0, 0, 0)", mark.evaluate("node => getComputedStyle(node).backgroundColor"))
            page.set_viewport_size({"width": 420, "height": 1000})
            self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 420)
            self.assertEqual("Second synthetic passage", mark.inner_text())
            page.keyboard.press("Escape")
            self.assertEqual(1, page.evaluate("window.__ANCHOR_READER_TEST__.returns"))

            page.evaluate("window.__ANCHOR_READER_TEST__.mount(false)")
            page.get_by_text("Unlock the project to inspect its source passages.", exact=True).wait_for()
            self.assertNotIn("Second synthetic passage", page.inner_text("body"))
            page.evaluate("window.__ANCHOR_READER_TEST__.mount(true)")
            open_anchor.wait_for()
            self.assertEqual(0, mark.count())
            open_anchor.click()
            mark.wait_for()
            self.assertEqual("Second synthetic passage", mark.inner_text())

            page.evaluate("window.__ANCHOR_READER_TEST__.holdRead = true")
            open_anchor.click()
            page.wait_for_function("window.__ANCHOR_READER_TEST__.releaseRead !== null")
            page.evaluate("window.__ANCHOR_READER_TEST__.mount(false)")
            page.get_by_text("Unlock the project to inspect its source passages.", exact=True).wait_for()
            page.evaluate("window.__ANCHOR_READER_TEST__.releaseRead()")
            page.wait_for_function("document.querySelector('mark') === null")
            self.assertNotIn("Second synthetic passage", page.inner_text("body"))

            page.evaluate(
                "window.__ANCHOR_READER_TEST__.holdRead = false; "
                "window.__ANCHOR_READER_TEST__.denyRead = true; window.__ANCHOR_READER_TEST__.mount(true)"
            )
            open_anchor.wait_for()
            open_anchor.click()
            page.get_by_text(
                "This anchor is unavailable or no longer permitted. No different passage was substituted.", exact=True
            ).wait_for()
            self.assertEqual(0, mark.count())
            calls = page.evaluate("window.__ANCHOR_READER_TEST__.calls")
            self.assertTrue(calls)
            for call in calls:
                self.assertTrue(call["command"].startswith("document_reader_"))
                self.assertFalse({"root", "actorId", "sessionId", "quote", "pageRegion"} & call["request"].keys())


if __name__ == "__main__":
    unittest.main(verbosity=2)
