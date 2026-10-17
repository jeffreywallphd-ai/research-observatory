"""Focused real-browser review qualification; run explicitly with installed Chromium.

This is outside ordinary foundation discovery so unrelated work needs no browser.
It tests the actual read-only server/assets against disposable canonical sources.
No product UI, full accessibility certification or immutable approval is implied.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests/foundation"))
import test_plan_review_server as http_fixture  # noqa: E402


class PlanningReviewBrowserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = http_fixture.LiveReviewTests("test_gate_conditions_and_legacy_amendment_identity_remain_visible")
        try:
            self.fixture.setUp()
        except BaseException:
            self.fixture.doCleanups()
            raise
        self.addCleanup(self.fixture.doCleanups)
        runtime = sync_playwright().start()
        self.addCleanup(runtime.stop)
        browser = runtime.chromium.launch(headless=True)
        self.addCleanup(browser.close)
        self.context = browser.new_context(viewport={"width": 1440, "height": 1000})
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.errors: list[str] = []
        self.requests: list[str] = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.on("request", lambda request: self.requests.append(request.url))
        self.base = f"http://127.0.0.1:{self.fixture.server.server_port}"

    def tearDown(self) -> None:
        self.assertEqual([], self.errors)
        self.assertTrue(all(url.startswith(self.base + "/") for url in self.requests))

    def test_navigation_gate_conditions_inert_text_and_keyboard_landmarks(self) -> None:
        page = self.page
        page.goto(self.base + "/waves/W3.html")
        page.locator("main a[href='/CAP-06/CAP-06.S01.html']").click()
        expect(page.get_by_role("heading", name="Lexical", exact=True)).to_be_visible()
        self.assertIn("Traceable lexical retrieval", page.locator("main").inner_text())
        self.assertIn("CAP-05.S01", page.locator("main").inner_text())
        page.locator("main a[href='/CAP-06/CAP-06.S01.T01.html']").click()
        expect(page.get_by_role("heading", name="<script>unsafe()</script>", exact=True)).to_be_visible()
        self.assertEqual(0, page.locator("main script, main img").count())
        page.goto(self.base + "/CAP-06/index.html")
        summary = page.locator("main details summary").filter(has_text="Canonical plan").first
        summary.focus()
        page.keyboard.press("Enter")
        self.assertIn("<script>unsafe()</script>", page.locator("main pre").first.inner_text())
        self.assertEqual(0, page.locator("main script, main img").count())
        page.goto(self.base + "/gates/G3.html")
        expect(page.get_by_role("heading", name="Evidence workbench", exact=True)).to_be_visible()
        self.assertIn("Fresh full qualification", page.locator("main").inner_text())
        self.assertIn("W4", page.locator("main").inner_text())
        page.keyboard.press("Tab")
        expect(page.locator(".skip")).to_be_focused()
        page.keyboard.press("Enter")
        expect(page.locator("main")).to_be_focused()
        session = self.context.new_cdp_session(page)
        tree = session.send("Accessibility.getFullAXTree")
        roles = {node.get("role", {}).get("value") for node in tree["nodes"]}
        self.assertTrue({"main", "navigation", "heading", "button", "searchbox"} <= roles)
        session.detach()
        self.capture("gate-keyboard-landmarks.png")

    def test_real_periodic_update_preserves_disclosure_focus_and_invalid_data_clears_view(self) -> None:
        page = self.page
        page.goto(self.base + "/CAP-06/CAP-06.S01.T01.html")
        expect(page.get_by_role("heading", name="<script>unsafe()</script>", exact=True)).to_be_visible()
        summary = page.locator("main details summary").first
        summary.focus()
        page.keyboard.press("Enter")
        self.assertIsNotNone(page.locator("main details").first.get_attribute("open"))
        self.fixture.data["capabilities"][0]["slices"][0]["tasks"][0]["status"] = "DONE"
        self.fixture.write_backlog()
        # Real visible-page15s scheduling, actual changed YAML and actual HTTP/DOM.
        page.get_by_text("State: DONE", exact=True).wait_for(timeout=20000)
        expect(summary).to_be_focused()
        self.assertIsNotNone(page.locator("main details").first.get_attribute("open"))
        self.capture("live-update-focus.png")
        (self.fixture.root / "planning/backlog.yaml").write_text("waves: [broken", encoding="utf-8")
        page.get_by_role("button", name="Refresh", exact=True).click()
        expect(page.get_by_role("heading", name="Current planning could not be displayed", exact=True)).to_be_visible()
        self.assertEqual(0, page.get_by_text("State: DONE", exact=True).count())
        self.fixture.write_backlog()
        page.get_by_role("button", name="Refresh", exact=True).click()
        expect(page.get_by_text("State: DONE", exact=True)).to_be_visible()

    def capture(self, name: str) -> None:
        output = os.environ.get("RO_REVIEW_BROWSER_OUTPUT")
        if not output:
            return
        destination = Path(output).resolve()
        destination.relative_to((REPO / "artifacts/tmp").resolve())
        destination.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(destination / name), full_page=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
