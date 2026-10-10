"""Production component interactions with authored ports; no principal proof."""

import os
import re
import unittest
from pathlib import Path
from typing import ClassVar

from playwright.sync_api import Browser, Playwright, sync_playwright

ROOT = Path(__file__).resolve().parents[2]


class ParsingQualityInteractionsTests(unittest.TestCase):
    directory: ClassVar[Path]
    runtime: ClassVar[Playwright]
    browser: ClassVar[Browser]

    @classmethod
    def setUpClass(cls):
        cls.directory = Path(os.environ["RO_QUALITY_UI_FIXTURE"]).resolve(strict=True)
        if not cls.directory.is_relative_to((ROOT / "artifacts/tmp").resolve()):
            raise RuntimeError("Owned ignored fixture required")
        cls.runtime = sync_playwright().start()
        cls.browser = cls.runtime.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.runtime.stop()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1280, "height": 900})
        self.addCleanup(self.context.close)
        self.errors: list[str] = []

        def route(request):
            url = request.request.url
            if not url.startswith("http://tauri.localhost/"):
                request.abort()
                return
            name = url.removeprefix("http://tauri.localhost/")
            if name == "index.html":
                css = "".join(f'<link rel="stylesheet" href="/{p.name}">' for p in self.directory.glob("*.css"))
                request.fulfill(
                    status=200,
                    content_type="text/html",
                    body="<!doctype html><html><head>"
                    + css
                    + '</head><body><main id="root"></main>'
                    + '<script type="module" src="/parsing-quality.js"></script></body></html>',
                )
                return
            path = (self.directory / name).resolve()
            if not path.is_relative_to(self.directory) or not path.is_file():
                request.abort()
                return
            request.fulfill(
                status=200,
                content_type="text/javascript" if path.suffix == ".js" else "text/css",
                body=path.read_bytes(),
            )

        self.context.route("**/*", route)
        self.page = self.context.new_page()
        self.page.set_default_timeout(7000)
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.goto("http://tauri.localhost/index.html")
        self.page.get_by_role("button", name=re.compile("^Inspect parse ")).click()
        self.page.get_by_role("button", name="Correct object 1", exact=True).wait_for()

    def propose(self):
        button = self.page.get_by_role("button", name="Correct object 1", exact=True)
        button.focus()
        self.page.keyboard.press("Enter")
        self.page.get_by_label("Human section label", exact=True).fill("SYNTHETIC human label 📚")
        self.page.get_by_role("button", name="Add proposed correction", exact=True).click()
        self.page.get_by_label("Correction rationale", exact=True).fill("SYNTHETIC reason for human correction")

    def test_saved_preview_explicit_acceptance_themes_keyboard_and_reader_return(self):
        self.assertIn("unknown", self.page.get_by_text("sections", exact=True).locator("..").inner_text())
        self.assertIn("<script>", self.page.get_by_role("region", name="Accepted structure", exact=True).inner_text())
        self.assertEqual(0, self.page.locator("script:not([src])").count())
        self.propose()
        self.assertFalse(
            self.page.get_by_role("button", name="Open accepted revision in Reader", exact=True).is_enabled()
        )
        self.page.get_by_role("button", name="Save proposal and preview", exact=True).click()
        self.page.get_by_text(
            "Proposal saved and previewed. The accepted revision and downstream state are unchanged.", exact=True
        ).wait_for()
        self.assertIn(
            "SYNTHETIC human label", self.page.get_by_role("region", name="Proposed structure", exact=True).inner_text()
        )
        self.assertNotIn(
            "SYNTHETIC human label", self.page.get_by_role("region", name="Accepted structure", exact=True).inner_text()
        )
        for theme in ("light", "dark"):
            self.page.evaluate("theme=>document.documentElement.dataset.theme=theme", theme)
            self.page.set_viewport_size({"width": 480, "height": 900})
            self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), 480)
        self.page.get_by_role("button", name="Preview current impact", exact=True).click()
        accept = self.page.get_by_role("button", name="Accept exact saved correction", exact=True)
        self.assertFalse(accept.is_enabled())
        self.page.get_by_role("checkbox", name=re.compile("^I accept this exact saved proposal")).check()
        accept.click()
        self.page.get_by_text("Correction explicitly accepted.", exact=False).wait_for()
        self.assertIn(
            "SYNTHETIC human label", self.page.get_by_role("region", name="Accepted structure", exact=True).inner_text()
        )
        self.assertEqual(
            ["save", "accept"],
            self.page.evaluate(
                "window.__QUALITY_UI_TEST__.calls.filter(c=>['save','accept'].includes(c.action)).map(c=>c.action)"
            ),
        )
        self.page.get_by_role("button", name="Open accepted revision in Reader", exact=True).click()
        self.page.get_by_text(
            "Open a local project to review parsing quality and saved corrections.", exact=True
        ).wait_for()
        self.assertTrue(self.page.evaluate("window.__QUALITY_UI_TEST__.returns[0].revisionId.endsWith('000000000fa3')"))
        self.assertFalse(self.errors)

    def test_undo_discard_and_exact_unknown_command_recovery(self):
        self.propose()
        self.page.get_by_role("button", name="Undo last proposed operation", exact=True).click()
        self.assertIn("0 proposed operations", self.page.get_by_text("0 proposed operations", exact=False).inner_text())
        self.page.get_by_role("button", name="Add proposed correction", exact=True).click()
        self.page.evaluate("window.__QUALITY_UI_TEST__.unknown=true")
        self.page.get_by_role("button", name="Save proposal and preview", exact=True).click()
        self.page.get_by_role("button", name="Retry exact pending command", exact=True).wait_for()
        self.assertFalse(self.page.get_by_role("button", name="Save proposal and preview", exact=True).is_enabled())
        self.page.evaluate("window.__QUALITY_UI_TEST__.unknown=false")
        self.page.get_by_role("button", name="Retry exact pending command", exact=True).click()
        self.page.get_by_text("Proposal saved and previewed.", exact=False).wait_for()
        self.assertTrue(
            self.page.evaluate(
                "(()=> {const c=window.__QUALITY_UI_TEST__.calls.filter(c=>c.action==='save');"
                "return JSON.stringify(c[0])===JSON.stringify(c[1]);})()"
            )
        )
        self.page.get_by_role("button", name="Discard saved proposal", exact=True).click()
        self.page.get_by_text("Proposal discarded with a retained human rationale.", exact=False).wait_for()
        self.assertIn(
            "No saved proposal", self.page.get_by_role("region", name="Proposed structure", exact=True).inner_text()
        )
        self.assertFalse(self.errors)

    def test_lock_discards_late_saved_proposal_and_denied_state_has_no_content(self):
        self.propose()
        self.page.evaluate("window.__QUALITY_UI_TEST__.hold=true")
        self.page.get_by_role("button", name="Save proposal and preview", exact=True).click()
        self.page.wait_for_function("window.__QUALITY_UI_TEST__.release !== null")
        self.page.evaluate("window.__QUALITY_NATIVE_WITNESS__.mount(false);window.__QUALITY_UI_TEST__.release()")
        self.page.get_by_text(
            "Open a local project to review parsing quality and saved corrections.", exact=True
        ).wait_for()
        self.assertEqual(0, self.page.get_by_role("region", name="Proposed structure", exact=True).count())
        self.assertNotIn("SYNTHETIC reason", self.page.locator("body").inner_text())
        self.assertFalse(self.errors)
