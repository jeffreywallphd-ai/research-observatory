"""Actual root and reprocessing controls; authored ports, no Native claim."""

import os
import re
import unittest
from pathlib import Path
from typing import ClassVar

from playwright.sync_api import Browser, Playwright, sync_playwright

ROOT = Path(__file__).resolve().parents[2]


class ReprocessingWorkflowNavigationTests(unittest.TestCase):
    directory: ClassVar[Path]
    runtime: ClassVar[Playwright]
    browser: ClassVar[Browser]

    @classmethod
    def setUpClass(cls):
        cls.directory = Path(os.environ["RO_REPROCESSING_NAVIGATION_FIXTURE"]).resolve(strict=True)
        if not cls.directory.is_relative_to((ROOT / "artifacts/tmp").resolve()):
            raise RuntimeError("Owned ignored fixture required")
        cls.runtime = sync_playwright().start()
        cls.browser = cls.runtime.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.runtime.stop()

    def test_actual_pending_reconciliation_guards_guided_stage_and_return(self):
        for mode in ("dirty", "busy", "unknown"):
            for route in ("stage", "return", "workspace", "home", "settings", "command-shortcut"):
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
                                    + '<script type="module" src="/reprocessing-navigation.js"></script>',
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
                        page.set_default_timeout(7000)
                        page.goto("http://tauri.localhost/index.html")
                        page.locator("[data-all-tools] > summary").click()
                        page.get_by_role("button", name="Local projects", exact=True).click()
                        page.get_by_role("button", name="Open synthetic fixture project", exact=True).click()
                        page.get_by_text("Synthetic workflow", exact=True).wait_for()
                        if not page.locator("[data-all-tools]").evaluate("e=>e.open"):
                            page.locator("[data-all-tools] > summary").click()
                        page.get_by_role("button", name="Parsing Quality & Corrections", exact=True).click()
                        page.get_by_role("button", name=re.compile("^Inspect parse ")).click()
                        page.get_by_role("checkbox", name=re.compile("^Document revision ")).check()
                        page.get_by_role("button", name="Reprocess selected", exact=True).click()
                        page.get_by_role("button", name="Compare this document", exact=True).click()
                        page.get_by_role("combobox", name=re.compile("^Candidate target")).select_option(index=1)
                        page.get_by_label("Reconciliation rationale", exact=True).fill(
                            "SYNTHETIC exact reprocessing navigation rationale"
                        )
                        if mode != "dirty":
                            page.evaluate(
                                "mode=>{window.__REPROCESSING_UI_TEST__.hold=mode==='busy';window.__REPROCESSING_UI_TEST__.unknown=mode==='unknown';}",
                                mode,
                            )
                            page.get_by_role("button", name="Save exact reconciliation and impact", exact=True).click()
                            if mode == "busy":
                                page.wait_for_function("window.__REPROCESSING_UI_TEST__.release !== null")
                            else:
                                page.get_by_role(
                                    "button", name="Retry exact pending reprocessing command", exact=True
                                ).wait_for()
                        owner = page.get_by_role("region", name="Parsing Quality and Corrections", exact=True)
                        page.wait_for_function("window.__REPROCESSING_UI_TEST__.blocked")
                        before = page.evaluate("JSON.stringify(window.__REPROCESSING_UI_TEST__.calls)")
                        rationale = page.get_by_role("region", name="Reparse comparison", exact=True).get_by_role(
                            "textbox"
                        )
                        self.assertEqual("SYNTHETIC exact reprocessing navigation rationale", rationale.input_value())
                        if route == "stage":
                            target = page.locator("[data-workflow-stage-key] > button")
                        elif route == "return":
                            target = page.get_by_role(
                                "button", name="Return to current step · Synthetic current stage", exact=True
                            )
                        elif route == "workspace":
                            target = page.get_by_role("button", name="Source Manager", exact=True)
                        elif route == "settings":
                            target = page.locator("[data-application-settings-trigger]")
                        else:
                            target = page.get_by_role("button", name="Project home", exact=True)

                        def navigate():
                            if route == "command-shortcut":
                                page.keyboard.press("Control+k")
                            else:
                                target.click()

                        def settle_announcement():
                            page.evaluate(
                                "() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
                            )

                        navigate()
                        settle_announcement()
                        self.assertEqual(
                            "Save or undo the local correction, and resolve a pending command, before leaving Parsing Quality.",
                            page.locator("[data-live-region]").inner_text(),
                        )
                        self.assertEqual(1, owner.count())
                        self.assertEqual(0, page.evaluate("window.__REPROCESSING_ROOT_TEST__.unmounted"))
                        self.assertEqual(before, page.evaluate("JSON.stringify(window.__REPROCESSING_UI_TEST__.calls)"))
                        self.assertEqual("SYNTHETIC exact reprocessing navigation rationale", rationale.input_value())
                        self.assertEqual(0, page.evaluate("window.__REPROCESSING_UI_TEST__.acceptedCount"))
                        if mode == "dirty":
                            page.get_by_role("button", name="Undo unsaved reconciliation", exact=True).click()
                        elif mode == "busy":
                            page.evaluate(
                                "window.__REPROCESSING_UI_TEST__.hold=false;window.__REPROCESSING_UI_TEST__.release()"
                            )
                        else:
                            page.evaluate("window.__REPROCESSING_UI_TEST__.unknown=false")
                            page.get_by_role(
                                "button", name="Retry exact pending reprocessing command", exact=True
                            ).click()
                        page.wait_for_function("!window.__REPROCESSING_UI_TEST__.blocked")
                        if mode == "unknown":
                            commands = page.evaluate(
                                "window.__REPROCESSING_UI_TEST__.calls.filter(command => command.action === 'reconcile')"
                            )
                            self.assertEqual(2, len(commands))
                            self.assertEqual(commands[0], commands[1])
                            self.assertEqual(1, page.evaluate("window.__REPROCESSING_UI_TEST__.reconciledCount"))
                        navigate()
                        if route == "settings":
                            page.get_by_role("heading", name="Security & sign-in", exact=True).wait_for()
                        else:
                            owner.wait_for(state="detached")
                        settle_announcement()
                        if route == "workspace":
                            self.assertEqual("sources opened.", page.locator("[data-live-region]").inner_text())
                            self.assertEqual("page", target.get_attribute("aria-current"))
                        self.assertEqual(0, page.evaluate("window.__REPROCESSING_UI_TEST__.acceptedCount"))
                    finally:
                        context.close()


if __name__ == "__main__":
    unittest.main()
