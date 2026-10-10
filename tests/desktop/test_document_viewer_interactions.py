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
    def test_unavailable_reference_head_refreshes_without_displaying_stale_text(self):
        self.select_text()
        self.page.evaluate("window.__VIEWER_UI_TEST__.staleReferences=true")
        self.page.get_by_role("button", name="Inspect references", exact=True).click()
        self.page.get_by_text("no prior text was displayed", exact=False).wait_for()
        self.assertEqual(0, self.page.get_by_role("region", name="Reference 1", exact=True).count())
        self.page.get_by_role("button", name="Refresh reference matches", exact=True).click()
        self.page.get_by_role("region", name="Reference 1", exact=True).wait_for()
        calls = self.page.evaluate("window.__VIEWER_UI_TEST__.referenceCalls")
        self.assertEqual(["read", "enrich"], [call["kind"] for call in calls])
        self.assertIsNotNone(calls[1]["expected"])
        self.assertFalse(self.errors)

    def test_ambiguous_reference_read_keeps_admission_and_denies_unaccounted_retry(self):
        self.select_text()
        self.page.evaluate("window.__VIEWER_UI_TEST__.unknownReference=true")
        self.page.get_by_role("button", name="Inspect references", exact=True).click()
        self.page.get_by_text("Source view unavailable", exact=True).wait_for()
        self.assertEqual(1, len(self.page.evaluate("window.__VIEWER_UI_TEST__.referenceCalls")))
        self.assertEqual(0, self.page.get_by_role("region", name="Reference 1", exact=True).count())
        self.page.evaluate("window.__VIEWER_UI_TEST__.unknownReference=false")
        self.page.get_by_role("button", name="Retry current source status", exact=True).click()
        self.wait(lambda: self.page.get_by_role("button", name="Next page", exact=True).is_enabled())
        self.page.get_by_label("Accepted structured revision").select_option(index=1)
        self.page.get_by_role("button", name="Inspect references", exact=True).click()
        self.page.get_by_text("References exceed the local Reader limit", exact=False).wait_for()
        self.assertEqual(1, len(self.page.evaluate("window.__VIEWER_UI_TEST__.referenceCalls")))
        self.assertFalse(self.errors)

    def test_references_preserve_inert_text_current_source_and_opaque_commands(self):
        self.select_text()
        self.page.get_by_role("button", name="Inspect references", exact=True).click()
        self.page.get_by_role("button", name="Extract references", exact=True).click()
        reference = self.page.get_by_role("region", name="Reference 1", exact=True)
        self.assertIn("<script>", reference.inner_text())
        self.assertFalse(self.page.evaluate("Boolean(window.referenceExecuted)"))
        self.page.get_by_role("button", name="Jump to reference source", exact=True).click()
        self.page.wait_for_function("document.body.textContent.includes('Synthetic inert')")
        self.page.get_by_role("button", name="Return to selected Work/version", exact=True).click()
        self.assertEqual(0, self.page.get_by_role("region", name="Reference inspection", exact=True).count())
        calls = self.page.evaluate("window.__VIEWER_UI_TEST__.referenceCalls")
        self.assertEqual(["read", "enrich"], [call["kind"] for call in calls])
        self.assertEqual({"kind", "selectedRevision", "command", "expected"}, set(calls[1]))

    def test_reference_uncertainty_target_inspection_and_source_substitution_denial(self):
        self.select_text()
        self.page.evaluate(
            "window.__VIEWER_UI_TEST__.referenceExists=true; window.__VIEWER_UI_TEST__.referenceMode='candidate'"
        )
        self.page.get_by_role("button", name="Inspect references", exact=True).click()
        self.page.get_by_role("button", name="Inspect candidate Work", exact=True).click()
        self.assertIn(
            "Matched Work revision", self.page.get_by_role("region", name="Canonical reference target").inner_text()
        )
        self.assertIn(
            "human review required", self.page.get_by_role("region", name="Reference 1", exact=True).inner_text()
        )
        self.page.evaluate("window.__VIEWER_UI_TEST__.wrongReferenceSource=true")
        self.page.get_by_role("button", name="Inspect references", exact=True).click()
        self.page.wait_for_function("document.body.textContent.includes('no substitute collection')")
        self.assertEqual(0, self.page.get_by_role("region", name="Reference 1", exact=True).count())

    def test_lock_clears_late_reference_without_substituting_text(self):
        self.select_text()
        self.page.evaluate(
            "window.__VIEWER_UI_TEST__.referenceExists=true; window.__VIEWER_UI_TEST__.holdReference=true"
        )
        self.page.get_by_role("button", name="Inspect references", exact=True).click()
        self.page.wait_for_function("window.__VIEWER_UI_TEST__.releaseReference !== null")
        self.page.evaluate("window.__VIEWER_UI_TEST__.mount(false); window.__VIEWER_UI_TEST__.releaseReference()")
        self.assertEqual(0, self.page.get_by_role("region", name="Reference 1", exact=True).count())

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

    def test_two_anchors_unicode_geometry_zoom_reflow_and_exact_return(self):
        self.page.evaluate("() => { window.__VIEWER_UI_TEST__.anchorMode = true; }")
        self.page.get_by_label("Accepted structured revision").select_option(index=1)
        self.page.get_by_role("heading", name="Anchor 1 · Synthetic accepted source", exact=True).wait_for()
        self.page.get_by_role("heading", name="Anchor 2 · Synthetic accepted source", exact=True).wait_for()
        self.assertEqual(["📚", "chosen"], self.page.locator(".viewer-anchor-context mark").all_text_contents())
        self.wait(lambda: self.page.locator(".viewer-anchor-marker").count() == 2)
        self.assertEqual(["1", "2"], self.page.locator(".viewer-anchor-marker text").all_text_contents())
        self.assertEqual(2, self.page.evaluate("() => window.__VIEWER_UI_TEST__.anchorCalls"))
        self.assertNotIn("context", str(self.page.evaluate("() => window.__VIEWER_UI_TEST__.savedLinks")))
        self.page.get_by_label("Source zoom").select_option("1.5")
        self.wait(lambda: self.page.get_by_role("button", name="Next page", exact=True).is_enabled())
        self.assertEqual(2, self.page.locator(".viewer-anchor-marker").count())
        self.page.evaluate("() => document.documentElement.dataset.theme = 'dark'")
        self.page.set_viewport_size({"width": 500, "height": 900})
        self.assertLessEqual(self.page.evaluate("() => document.documentElement.scrollWidth"), 500)
        self.page.get_by_role("button", name="Go to anchor 2 on page 1", exact=True).focus()
        self.page.keyboard.press("Enter")
        self.page.keyboard.press("Escape")
        self.page.get_by_text("No open source", exact=True).wait_for()
        self.assertEqual(0, self.page.locator(".viewer-anchor-context").count())
        self.assertTrue(
            self.page.evaluate("() => window.__VIEWER_UI_TEST__.returns[0].versionRevisionId.endsWith('000b')")
        )
        self.assertFalse(self.errors)

    def test_saved_link_reopens_without_prior_handoff_and_missing_anchor_has_revision_and_source_review(self):
        self.page.evaluate("() => window.__VIEWER_UI_TEST__.mount(false)")
        self.page.get_by_text("No open source", exact=True).wait_for()
        self.page.evaluate(
            "() => { const s = window.__VIEWER_UI_TEST__; s.linkMode = true; s.noHandoff = true; "
            "s.missingAnchor = true; s.mount(); }"
        )
        self.page.get_by_role("heading", name="Anchor 1 · Synthetic accepted source", exact=True).wait_for()
        self.assertEqual(2, self.page.get_by_text("Anchor missing", exact=True).count())
        self.assertTrue(self.page.get_by_text("00000000-0000-7000-8000-000000000003", exact=True).first.is_visible())
        self.assertEqual(0, self.page.locator(".viewer-anchor-context mark").count())
        self.page.get_by_role("button", name="Review source for missing anchor", exact=True).first.click()
        self.page.get_by_text("No open source", exact=True).wait_for()
        self.assertTrue(
            self.page.evaluate("() => window.__VIEWER_UI_TEST__.returns[0].versionRevisionId.endsWith('000b')")
        )
        self.assertFalse(self.errors)

    def test_new_link_revision_replaces_context_with_and_without_prior_handoff(self):
        for no_handoff in (False, True):
            self.page.evaluate("() => window.__VIEWER_UI_TEST__.mount(false)")
            self.page.get_by_text("No open source", exact=True).wait_for()
            self.page.evaluate(
                "noHandoff => { const s = window.__VIEWER_UI_TEST__; s.linkMode = true; "
                "s.noHandoff = noHandoff; s.linkRevision = '00000000-0000-7000-8000-000000000003'; s.mount(); }",
                no_handoff,
            )
            self.page.get_by_role("heading", name="Anchor 2 · Synthetic accepted source", exact=True).wait_for()
            self.assertEqual(
                "00000000-0000-7000-8000-000000000003",
                self.page.get_by_label("Accepted structured revision").input_value(),
            )
            calls = self.page.evaluate("() => window.__VIEWER_UI_TEST__.anchorCalls")
            self.page.evaluate(
                "() => { const s = window.__VIEWER_UI_TEST__; "
                "s.linkRevision = '00000000-0000-7000-8000-000000000023'; s.mount(); }"
            )
            self.wait(
                lambda: (
                    self.page.get_by_label("Accepted structured revision").input_value()
                    == "00000000-0000-7000-8000-000000000023"
                )
            )
            self.page.get_by_role("heading", name="Anchor 2 · Synthetic accepted source", exact=True).wait_for()
            self.assertEqual(calls + 2, self.page.evaluate("() => window.__VIEWER_UI_TEST__.anchorCalls"))
            self.assertEqual(["📚", "chosen"], self.page.locator(".viewer-anchor-context mark").all_text_contents())
            self.assertEqual(
                2,
                self.page.locator(".viewer-anchor-context")
                .get_by_text("00000000-0000-7000-8000-000000000023", exact=True)
                .count(),
            )
        self.assertFalse(self.errors)

    def test_late_previous_link_revision_cannot_replace_new_context(self):
        self.page.evaluate("() => window.__VIEWER_UI_TEST__.mount(false)")
        self.page.get_by_text("No open source", exact=True).wait_for()
        self.page.evaluate(
            "() => { const s = window.__VIEWER_UI_TEST__; s.linkMode = true; s.noHandoff = true; "
            "s.holdAnchor = true; s.mount(); }"
        )
        self.wait(lambda: self.page.evaluate("() => typeof window.__VIEWER_UI_TEST__.releaseAnchor === 'function'"))
        self.page.evaluate(
            "() => { const s = window.__VIEWER_UI_TEST__; s.holdAnchor = false; "
            "s.linkRevision = '00000000-0000-7000-8000-000000000023'; s.mount(); }"
        )
        self.page.get_by_text("This anchor context exceeds the local Viewer limit.", exact=False).wait_for()
        self.assertEqual(0, self.page.locator(".viewer-anchor-context mark").count())
        self.assertEqual(1, self.page.evaluate("() => window.__VIEWER_UI_TEST__.anchorCalls"))
        self.page.evaluate("() => window.__VIEWER_UI_TEST__.releaseAnchor()")
        self.page.get_by_role("button", name="Retry current source status", exact=True).click()
        self.page.get_by_role("heading", name="Anchor 2 · Synthetic accepted source", exact=True).wait_for()
        self.wait(lambda: self.page.evaluate("() => window.__VIEWER_UI_TEST__.anchorCalls === 3"))
        self.assertEqual(
            "00000000-0000-7000-8000-000000000023",
            self.page.get_by_label("Accepted structured revision").input_value(),
        )
        self.assertEqual(
            2,
            self.page.locator(".viewer-anchor-context")
            .get_by_text("00000000-0000-7000-8000-000000000023", exact=True)
            .count(),
        )
        self.assertFalse(self.errors)

    def test_late_anchor_after_lock_and_substituted_source_cannot_publish_context(self):
        self.page.evaluate("() => { const s = window.__VIEWER_UI_TEST__; s.anchorMode = true; s.holdAnchor = true; }")
        self.page.get_by_label("Accepted structured revision").select_option(index=1)
        self.wait(lambda: self.page.evaluate("() => typeof window.__VIEWER_UI_TEST__.releaseAnchor === 'function'"))
        self.page.evaluate("() => window.__VIEWER_UI_TEST__.mount(false)")
        self.page.get_by_text("No open source", exact=True).wait_for()
        self.page.evaluate(
            "() => { const s = window.__VIEWER_UI_TEST__; s.holdAnchor = false; s.releaseAnchor(); "
            "s.wrongAnchorSource = true; s.mount(); }"
        )
        self.wait(lambda: self.page.get_by_role("button", name="Next page", exact=True).is_enabled())
        self.page.get_by_label("Accepted structured revision").select_option(index=1)
        self.page.get_by_text("An exact anchor is unavailable or no longer permitted.", exact=False).wait_for()
        self.assertEqual(0, self.page.locator(".viewer-anchor-context mark").count())
        self.assertFalse(self.errors)

    def test_rotated_geometry_and_mismatch_preserve_structural_context(self):
        for rotation in (90, 180, 270):
            self.page.evaluate("() => window.__VIEWER_UI_TEST__.mount(false)")
            self.page.get_by_text("No open source", exact=True).wait_for()
            self.page.evaluate(
                "r => { const s = window.__VIEWER_UI_TEST__; s.anchorRotation = r; s.linkMode = true; s.mount(); }",
                rotation,
            )
            self.page.get_by_role("heading", name="Anchor 2 · Synthetic accepted source", exact=True).wait_for()
            self.wait(lambda: self.page.locator(".viewer-anchor-marker").count() == 2)
        self.page.evaluate("() => window.__VIEWER_UI_TEST__.mount(false)")
        self.page.get_by_text("No open source", exact=True).wait_for()
        self.page.evaluate("() => { const s = window.__VIEWER_UI_TEST__; s.mismatchGeometry = true; s.mount(); }")
        self.page.get_by_role("heading", name="Anchor 2 · Synthetic accepted source", exact=True).wait_for()
        self.assertEqual(0, self.page.locator(".viewer-anchor-marker").count())
        self.assertEqual(2, self.page.get_by_text("Structural/text fallback:", exact=False).count())
        self.assertEqual(["📚", "chosen"], self.page.locator(".viewer-anchor-context mark").all_text_contents())
        self.assertFalse(self.errors)

    def test_ambiguous_anchor_transport_denies_context_and_unaccounted_retry(self):
        self.page.evaluate(
            "() => { const s = window.__VIEWER_UI_TEST__; s.anchorMode = true; s.unknownAnchor = true; }"
        )
        self.page.get_by_label("Accepted structured revision").select_option(index=1)
        self.page.get_by_text("Source view unavailable", exact=True).wait_for()
        self.assertEqual(1, self.page.evaluate("() => window.__VIEWER_UI_TEST__.anchorCalls"))
        self.assertEqual(0, self.page.locator(".viewer-anchor-context mark").count())
        self.page.evaluate("() => { window.__VIEWER_UI_TEST__.unknownAnchor = false; }")
        self.page.get_by_role("button", name="Retry current source status", exact=True).click()
        self.wait(lambda: self.page.get_by_role("button", name="Next page", exact=True).is_enabled())
        self.page.get_by_label("Accepted structured revision").select_option(index=1)
        self.page.get_by_text("This anchor context exceeds the local Viewer limit.", exact=False).wait_for()
        self.assertEqual(1, self.page.evaluate("() => window.__VIEWER_UI_TEST__.anchorCalls"))
        self.assertFalse(self.errors)

    def select_action_anchor(self):
        self.page.evaluate("() => window.__VIEWER_UI_TEST__.anchorMode = true")
        self.page.get_by_label("Accepted structured revision").select_option(index=1)
        self.page.get_by_role("button", name="Use anchor 1 for source actions", exact=True).click()
        return self.page.get_by_role("region", name="Rights-aware Reader actions", exact=True)

    def test_rights_review_is_explicit_separate_and_does_not_execute_output(self):
        pane = self.select_action_anchor()
        execute = pane.get_by_role("button", name="Copy selected quotation with source identifiers", exact=True)
        self.assertFalse(execute.is_enabled())
        pane.get_by_role("button", name="Check current permissions", exact=True).click()
        record = pane.get_by_role("button", name="Record permitted use only", exact=True)
        record.wait_for()
        self.assertFalse(record.is_enabled())
        pane.get_by_role("checkbox").check()
        record.click()
        pane.get_by_text("Permitted use recorded. No action was performed.", exact=False).wait_for()
        self.assertEqual(
            ["policy", "rights-review"],
            self.page.evaluate("() => window.__VIEWER_UI_TEST__.actionCalls.map(x => x.stage)"),
        )
        self.assertFalse(execute.is_enabled())
        pane.get_by_role("button", name="Check current permissions", exact=True).click()
        self.wait(execute.is_enabled)
        execute.click()
        pane.get_by_text("The explicit action completed.", exact=False).wait_for()
        calls = self.page.evaluate("() => window.__VIEWER_UI_TEST__.actionCalls")
        self.assertEqual(["policy", "rights-review", "policy", "execute"], [x["stage"] for x in calls])
        self.assertIsNone(calls[1]["anchorId"])
        self.assertIsNotNone(calls[-1]["anchorId"])
        self.assertTrue(
            all(not {"text", "quote", "actorId", "destination", "applicationPath"}.intersection(x) for x in calls)
        )
        self.assertFalse(self.errors)

    def test_alternate_copy_context_menu_and_print_shortcut_only_request_denial(self):
        self.select_action_anchor()
        for index, kind in enumerate(["copy", "contextmenu", "print"]):
            prevented = self.page.evaluate(
                """kind => {
              const el = document.querySelector('.protected-document-viewer');
              const event = kind === 'print' ? new KeyboardEvent('keydown',
                {key:'p',ctrlKey:true,bubbles:true,cancelable:true})
                : new Event(kind, {bubbles:true,cancelable:true});
              el.dispatchEvent(event); return event.defaultPrevented;
            }""",
                kind,
            )
            self.assertTrue(prevented)
            self.wait(lambda n=index: self.page.evaluate("() => window.__VIEWER_UI_TEST__.actionCalls.length") == n + 1)
            self.wait(lambda: self.page.evaluate("() => window.__VIEWER_UI_TEST__.activeActions.size") == 0)
        calls = self.page.evaluate("() => window.__VIEWER_UI_TEST__.actionCalls")
        self.assertTrue(all(x["stage"] == "denied-attempt" for x in calls))
        self.assertEqual("print-quotation", calls[-1]["action"])
        self.assertTrue(all(not {"text", "quote", "destination"}.intersection(x) for x in calls))
        self.assertFalse(self.errors)

    def test_unknown_action_closure_prevents_retry_and_never_claims_completion(self):
        pane = self.select_action_anchor()
        self.page.evaluate("() => window.__VIEWER_UI_TEST__.unknownAction = true")
        check = pane.get_by_role("button", name="Check current permissions", exact=True)
        check.click()
        pane.get_by_text("The issued action has not confirmed physical closure.", exact=False).wait_for()
        self.assertFalse(check.is_enabled())
        pane.get_by_role("button", name="Check completion / request cancellation", exact=True).click()
        pane.get_by_text("Cancellation requested.", exact=False).wait_for()
        self.assertEqual(1, self.page.evaluate("() => window.__VIEWER_UI_TEST__.actionCalls.length"))
        self.assertFalse(self.errors)

    def test_partial_output_warning_action_specific_permissions_and_source_return(self):
        pane = self.select_action_anchor()
        self.page.evaluate(
            "() => { const s=window.__VIEWER_UI_TEST__; "
            "s.actionPermissions['copy-quotation']=true; s.partialAction=true; }"
        )
        pane.get_by_role("button", name="Check current permissions", exact=True).click()
        copy = pane.get_by_role("button", name="Copy selected quotation with source identifiers", exact=True)
        self.wait(copy.is_enabled)
        copy.click()
        pane.get_by_text("The action was only partly confirmed.", exact=False).wait_for()
        pane.get_by_label("Reader source action").select_option("export-annotation")
        pane.get_by_text("it excludes quotation and surrounding text.", exact=False).wait_for()
        save = pane.get_by_role("button", name="Save anchor annotation without quoted text", exact=True)
        self.assertFalse(save.is_enabled())
        pane.get_by_role("button", name="Check current permissions", exact=True).click()
        pane.get_by_role("button", name="Record permitted use only", exact=True).wait_for()
        self.assertFalse(save.is_enabled())
        pane.get_by_role("button", name="Review selected source permissions", exact=True).click()
        self.page.get_by_text("No open source", exact=True).wait_for()
        self.assertEqual(1, self.page.evaluate("() => window.__VIEWER_UI_TEST__.returns.length"))
        self.assertFalse(self.errors)


if __name__ == "__main__":
    unittest.main(verbosity=2)
