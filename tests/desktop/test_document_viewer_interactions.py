"""Mounted approved reader journey with explicitly synthetic ports/PDF decoder.

This proves controls, inert text and protected-state clearing, not actual
Windows native transport, encrypted reads or decoder/memory qualification.
"""

import os
import time
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]


class DocumentViewerInteractionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = Path(os.environ["RO_VIEWER_UI_FIXTURE"])
        if not cls.directory.resolve().is_relative_to((REPO / "artifacts/tmp").resolve()):
            raise RuntimeError("Fixture must use owned ignored task output")
        cls.runtime = sync_playwright().start()
        cls.browser = cls.runtime.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.runtime.stop()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1280, "height": 900})
        self.addCleanup(self.context.close)
        self.requests, self.errors = [], []

        def route(request):
            url = request.request.url
            self.requests.append(url)
            if not url.startswith("http://tauri.localhost/"):
                request.abort()
                return
            name = url.removeprefix("http://tauri.localhost/")
            if name == "index.html":
                css = "".join(f'<link rel="stylesheet" href="/{path.name}">' for path in self.directory.glob("*.css"))
                request.fulfill(
                    status=200,
                    content_type="text/html",
                    body='<!doctype html><html><head><meta http-equiv="Content-Security-Policy" '
                    "content=\"default-src 'self'; script-src 'self'; worker-src 'self'; "
                    "connect-src 'self'; style-src 'self'\">" + css + '</head><body><main id="root"></main>'
                    '<script type="module" src="/document-viewer.js"></script></body></html>',
                )
                return
            path = (self.directory / name).resolve()
            if not path.is_relative_to(self.directory.resolve()) or not path.is_file():
                request.abort()
                return
            content_type = (
                "text/javascript"
                if path.suffix == ".js"
                else "text/css"
                if path.suffix == ".css"
                else "application/octet-stream"
            )
            request.fulfill(status=200, content_type=content_type, body=path.read_bytes())

        self.context.route("**/*", route)
        self.page = self.context.new_page()
        self.page.set_default_timeout(5000)
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.goto("http://tauri.localhost/index.html")
        self.wait(lambda: self.page.get_by_role("button", name="Next page", exact=True).is_enabled())

    def wait(self, condition):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(0.01)
        self.fail("Mounted viewer did not reach the expected state")

    def select_text(self):
        self.page.get_by_label("Accepted structured revision").select_option(index=1)
        button = self.page.get_by_role("button", name="paragraph · Synthetic element · page 2", exact=True)
        button.wait_for()
        return button

    def test_page_zoom_text_keyboard_return_and_responsive_regions(self):
        self.page.get_by_role("button", name="Next page", exact=True).click()
        self.wait(lambda: self.page.get_by_label("Source page", exact=True).input_value() == "2")
        self.page.get_by_label("Source zoom").select_option("1.5")
        self.select_text().click()
        self.page.get_by_text(
            "Synthetic inert <script>window.viewerDocumentExecuted=true</script> text", exact=True
        ).wait_for()
        self.assertFalse(self.page.evaluate("() => window.viewerDocumentExecuted === true"))
        self.assertTrue(self.page.get_by_role("article", name="Original source page").is_visible())
        self.assertTrue(self.page.get_by_text("Unverified extraction", exact=True).is_visible())
        self.assertTrue(
            self.page.evaluate("() => document.activeElement?.closest('.protected-document-viewer') !== null")
        )
        self.assertTrue(
            self.page.evaluate(
                "() => { const outline = document.querySelector('.document-outline'); "
                "return outline.scrollWidth <= outline.clientWidth; }"
            )
        )
        self.page.screenshot(path=str(self.directory / "reader-light.png"), full_page=True)
        self.page.evaluate("() => document.documentElement.dataset.theme = 'dark'")
        self.wait(
            lambda: self.page.evaluate("() => !document.getAnimations().some(value => value.playState === 'running')")
        )
        self.page.screenshot(path=str(self.directory / "reader-dark.png"), full_page=True)
        self.page.evaluate("() => document.documentElement.dataset.theme = 'light'")
        self.wait(
            lambda: self.page.evaluate("() => !document.getAnimations().some(value => value.playState === 'running')")
        )
        self.page.set_viewport_size({"width": 500, "height": 900})
        self.assertLessEqual(self.page.evaluate("() => document.documentElement.scrollWidth"), 500)
        self.page.screenshot(path=str(self.directory / "reader-narrow.png"), full_page=True)
        self.page.keyboard.press("Escape")
        self.page.get_by_text("No open source", exact=True).wait_for()
        self.assertEqual(1, self.page.evaluate("() => window.__VIEWER_UI_TEST__.returns.length"))
        self.assertTrue(
            self.page.evaluate("() => window.__VIEWER_UI_TEST__.returns[0].versionRevisionId.endsWith('000b')")
        )
        self.assertFalse(self.errors)

    def test_late_text_after_lock_and_cancelled_search_are_never_published(self):
        self.page.evaluate("() => { window.__VIEWER_UI_TEST__.holdSearch = true; }")
        self.page.get_by_label("Find in PDF page text").fill("Synthetic")
        self.page.get_by_role("button", name="Find next", exact=True).click()
        self.page.get_by_role("button", name="Cancel search", exact=True).click()
        self.page.evaluate("() => window.__VIEWER_UI_TEST__.releaseSearch()")
        time.sleep(0.05)
        self.assertEqual("1", self.page.get_by_label("Source page", exact=True).input_value())
        self.page.evaluate("() => { window.__VIEWER_UI_TEST__.holdText = true; }")
        self.select_text().click()
        self.wait(lambda: self.page.evaluate("() => typeof window.__VIEWER_UI_TEST__.releaseText === 'function'"))
        self.page.evaluate("() => window.__VIEWER_UI_TEST__.mount(false)")
        self.page.get_by_text("No open source", exact=True).wait_for()
        self.page.evaluate("() => window.__VIEWER_UI_TEST__.releaseText()")
        time.sleep(0.05)
        self.assertFalse(self.page.get_by_text("Synthetic inert", exact=False).count())
        self.assertGreater(self.page.evaluate("() => window.__VIEWER_UI_TEST__.closes"), 0)
        self.assertFalse(self.errors)

    def test_exact_source_substitution_denies_then_fresh_retry_recovers(self):
        self.page.evaluate("() => { window.__VIEWER_UI_TEST__.substituteSource = true; }")
        self.page.get_by_role("button", name="Retry current source status", exact=True).click()
        self.page.get_by_text("Source view unavailable", exact=True).wait_for()
        self.assertEqual(0, self.page.locator("canvas[role=img]").count())
        self.assertFalse(self.page.get_by_role("button", name="Next page", exact=True).is_enabled())
        self.page.evaluate("() => { window.__VIEWER_UI_TEST__.substituteSource = false; }")
        self.page.get_by_role("button", name="Retry current source status", exact=True).click()
        self.wait(lambda: self.page.get_by_role("button", name="Next page", exact=True).is_enabled())
        self.assertEqual(3, self.page.evaluate("() => window.__VIEWER_UI_TEST__.sourceCalls"))
        prevented = self.page.evaluate(
            "() => { const event = new Event('copy', { bubbles: true, cancelable: true }); "
            "document.querySelector('.protected-document-viewer').dispatchEvent(event); "
            "return event.defaultPrevented; }"
        )
        self.assertTrue(prevented)
        self.assertFalse(any(not url.startswith("http://tauri.localhost/") for url in self.requests))
        self.assertFalse(self.errors)

    def test_optional_revision_lookup_waits_for_first_page_and_stays_available_afterwards(self):
        self.wait(lambda: self.page.evaluate("() => window.__VIEWER_UI_TEST__.revisionCalls === 1"))
        self.page.evaluate("() => { window.__VIEWER_UI_TEST__.holdRender = true; }")
        self.page.get_by_role("button", name="Retry current source status", exact=True).click()
        self.wait(lambda: self.page.evaluate("() => typeof window.__VIEWER_UI_TEST__.releaseRender === 'function'"))
        self.assertEqual(1, self.page.evaluate("() => window.__VIEWER_UI_TEST__.revisionCalls"))
        self.assertFalse(self.page.get_by_role("button", name="Next page", exact=True).is_enabled())
        self.page.evaluate(
            "() => { window.__VIEWER_UI_TEST__.holdRender = false; window.__VIEWER_UI_TEST__.releaseRender(); }"
        )
        self.wait(lambda: self.page.get_by_role("button", name="Next page", exact=True).is_enabled())
        self.wait(lambda: self.page.evaluate("() => window.__VIEWER_UI_TEST__.revisionCalls === 2"))
        self.select_text().click()
        self.page.get_by_text("Unverified extraction", exact=True).wait_for()
        self.assertFalse(self.errors)

    def test_structured_resource_denial_retains_original_navigation_and_recovers(self):
        self.page.evaluate("() => { window.__VIEWER_UI_TEST__.limitOutline = true; }")
        self.page.get_by_label("Accepted structured revision").select_option(index=1)
        self.page.get_by_text("This structured view exceeds the local viewer limit.", exact=False).wait_for()
        self.assertTrue(self.page.get_by_role("button", name="Next page", exact=True).is_enabled())
        self.assertTrue(self.page.locator("canvas[role=img]").is_visible())
        self.page.get_by_role("button", name="Next page", exact=True).click()
        self.wait(lambda: self.page.get_by_label("Source page", exact=True).input_value() == "2")
        self.page.evaluate("() => { window.__VIEWER_UI_TEST__.limitOutline = false; }")
        self.page.get_by_label("Accepted structured revision").select_option(index=0)
        element = self.select_text()
        self.page.evaluate("() => { window.__VIEWER_UI_TEST__.limitText = true; }")
        element.click()
        self.page.get_by_text("This structured view exceeds the local viewer limit.", exact=False).wait_for()
        self.assertFalse(self.page.get_by_text("Synthetic inert", exact=False).count())
        self.assertTrue(self.page.get_by_role("button", name="Next page", exact=True).is_enabled())
        self.page.evaluate("() => { window.__VIEWER_UI_TEST__.limitText = false; }")
        element.click()
        self.page.get_by_text("Unverified extraction", exact=True).wait_for()
        self.assertFalse(self.errors)

    def test_retry_keeps_previous_structured_ipc_charge_until_its_real_settlement(self):
        self.page.evaluate("() => { window.__VIEWER_UI_TEST__.holdText = true; }")
        self.select_text().click()
        self.wait(lambda: self.page.evaluate("() => typeof window.__VIEWER_UI_TEST__.releaseText === 'function'"))
        self.page.get_by_role("button", name="Retry current source status", exact=True).click()
        self.wait(lambda: self.page.get_by_role("button", name="Next page", exact=True).is_enabled())
        self.page.get_by_label("Accepted structured revision").select_option(index=1)
        self.page.get_by_text("This structured view exceeds the local viewer limit.", exact=False).wait_for()
        self.page.evaluate(
            "() => { window.__VIEWER_UI_TEST__.holdText = false; window.__VIEWER_UI_TEST__.releaseText(); }"
        )
        self.page.get_by_label("Accepted structured revision").select_option(index=0)
        self.select_text().click()
        self.page.get_by_text("Unverified extraction", exact=True).wait_for()
        self.assertFalse(self.errors)


if __name__ == "__main__":
    unittest.main(verbosity=2)
