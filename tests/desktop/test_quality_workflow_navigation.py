"""Production root callbacks with explicit child/transport doubles; no Native proof."""

import os
import unittest
from pathlib import Path
from typing import ClassVar

from playwright.sync_api import Browser, Playwright, sync_playwright

ROOT = Path(__file__).resolve().parents[2]


class QualityWorkflowNavigationTests(unittest.TestCase):
    directory: ClassVar[Path]
    runtime: ClassVar[Playwright]
    browser: ClassVar[Browser]

    @classmethod
    def setUpClass(cls):
        cls.directory = Path(os.environ["RO_QUALITY_NAVIGATION_FIXTURE"]).resolve(strict=True)
        if not cls.directory.is_relative_to((ROOT / "artifacts/tmp").resolve()):
            raise RuntimeError("Owned ignored fixture required")
        cls.runtime = sync_playwright().start()
        cls.browser = cls.runtime.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.runtime.stop()

    def test_guided_stage_and_return_keep_dirty_busy_and_unknown_command_ownership(self):
        for mode in ("dirty", "busy", "unknown"):
            for route in ("stage", "return"):
                with self.subTest(mode=mode, route=route):
                    context = self.browser.new_context(viewport={"width": 1280, "height": 900})
                    try:

                        def serve(request):
                            url = request.request.url
                            if not url.startswith("http://tauri.localhost/"):
                                request.abort()
                                return
                            name = url.removeprefix("http://tauri.localhost/")
                            if name == "index.html":
                                css = "".join(
                                    f'<link rel="stylesheet" href="/{p.name}">' for p in self.directory.glob("*.css")
                                )
                                request.fulfill(
                                    content_type="text/html",
                                    body=css
                                    + '<div id="root"></div>'
                                    + '<script type="module" src="/quality-navigation.js"></script>',
                                )
                                return
                            path = (self.directory / name).resolve()
                            if not path.is_relative_to(self.directory) or not path.is_file():
                                request.abort()
                                return
                            request.fulfill(
                                content_type="text/javascript" if path.suffix == ".js" else "text/css",
                                body=path.read_bytes(),
                            )

                        context.route("**/*", serve)
                        page = context.new_page()
                        page.set_default_timeout(5000)
                        page.goto("http://tauri.localhost/index.html")
                        page.locator("[data-all-tools] > summary").click()
                        page.get_by_role("button", name="Local projects", exact=True).click()
                        page.get_by_role("button", name="Open synthetic fixture project", exact=True).click()
                        page.get_by_text("Synthetic workflow", exact=True).wait_for()
                        if not page.locator("[data-all-tools]").evaluate("e=>e.open"):
                            page.locator("[data-all-tools] > summary").click()
                        page.get_by_role("button", name="Parsing Quality & Corrections", exact=True).click()
                        owner = page.get_by_role("region", name="Synthetic correction ownership")
                        owner.wait_for()
                        page.get_by_role("button", name=f"Set correction {mode}", exact=True).click()
                        command = page.locator("[data-owned-command]").inner_text()
                        target = (
                            page.locator("[data-workflow-stage-key] > button")
                            if route == "stage"
                            else page.get_by_role(
                                "button", name="Return to current step · Synthetic current stage", exact=True
                            )
                        )
                        target.click()
                        self.assertEqual(1, owner.count())
                        self.assertEqual(command, page.locator("[data-owned-command]").inner_text())
                        self.assertEqual(0, page.evaluate("window.__QUALITY_NAVIGATION_TEST__.unmounted"))
                        page.get_by_role("button", name="Set correction clean", exact=True).click()
                        target.click()
                        owner.wait_for(state="detached")
                    finally:
                        context.close()


if __name__ == "__main__":
    unittest.main()
