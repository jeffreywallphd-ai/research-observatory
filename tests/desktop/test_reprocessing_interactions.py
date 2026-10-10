"""Production reprocessing components with explicit authored ports, no principal claim."""

import os
import re
import unittest
from pathlib import Path
from typing import ClassVar

from playwright.sync_api import Browser, Playwright, sync_playwright

ROOT = Path(__file__).resolve().parents[2]


class ReprocessingInteractionsTests(unittest.TestCase):
    directory: ClassVar[Path]
    runtime: ClassVar[Playwright]
    browser: ClassVar[Browser]

    @classmethod
    def setUpClass(cls):
        cls.directory = Path(os.environ["RO_REPROCESSING_UI_FIXTURE"]).resolve(strict=True)
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
                    + '<script type="module" src="/reprocessing.js"></script></body></html>',
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
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.goto("http://tauri.localhost/index.html")
        self.page.get_by_role("button", name=re.compile("^Inspect parse ")).click()
        self.page.get_by_role("button", name="Correct object 1", exact=True).wait_for()

    def ready_plan(self):
        self.page.get_by_role("checkbox", name=re.compile("^Document revision ")).check()
        self.page.get_by_role("button", name="Reprocess selected", exact=True).click()
        self.page.get_by_role("button", name="Compare this document", exact=True).click()
        self.page.get_by_role("combobox", name=re.compile("^Candidate target")).select_option(index=1)
        self.page.get_by_label("Reconciliation rationale", exact=True).fill(
            "SYNTHETIC carry forward reviewed human correction"
        )
        self.page.get_by_role("button", name="Save exact reconciliation and impact", exact=True).click()
        self.page.get_by_role("checkbox", name=re.compile("^I approve this exact saved reconciliation")).check()

    def test_explicit_acceptance_inert_content_themes_and_reader_return(self):
        self.ready_plan()
        self.assertEqual(0, self.page.evaluate("window.__REPROCESSING_UI_TEST__.acceptedCount"))
        self.assertIn("<script>", self.page.get_by_role("region", name="Reparse comparison", exact=True).inner_text())
        self.assertEqual(0, self.page.locator("script:not([src])").count())
        for theme in ("light", "dark"):
            self.page.evaluate("theme=>document.documentElement.dataset.theme=theme", theme)
            self.page.set_viewport_size({"width": 480, "height": 900})
            self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), 480)
        self.page.get_by_role("button", name="Approve exact reparse for this document", exact=True).click()
        self.page.get_by_text("Only affected downstream records were invalidated", exact=False).wait_for()
        self.assertEqual(1, self.page.evaluate("window.__REPROCESSING_UI_TEST__.acceptedCount"))
        self.page.get_by_role("button", name="Open accepted revision in Reader", exact=True).click()
        self.page.get_by_text(
            "Open a local project to review parsing quality and saved corrections.", exact=True
        ).wait_for()
        self.assertTrue(
            self.page.evaluate(
                "window.__REPROCESSING_UI_TEST__.returns[0].jobId === window.__REPROCESSING_UI_TEST__.expectedJobId"
            )
        )
        self.assertFalse(self.errors)

    def test_lost_post_commit_reply_retains_exact_command_and_blocks_navigation(self):
        self.ready_plan()
        self.page.evaluate("window.__REPROCESSING_UI_TEST__.unknown=true")
        self.page.get_by_role("button", name="Approve exact reparse for this document", exact=True).click()
        self.page.get_by_role("button", name="Retry exact pending reprocessing command", exact=True).wait_for()
        self.assertTrue(self.page.evaluate("window.__REPROCESSING_UI_TEST__.blocked"))
        self.assertFalse(
            self.page.get_by_role("button", name="Open accepted revision in Reader", exact=True).is_enabled()
        )
        self.assertFalse(self.page.get_by_role("button", name="Correct object 1", exact=True).is_enabled())
        self.page.evaluate("window.__REPROCESSING_UI_TEST__.unknown=false")
        self.page.get_by_role("button", name="Retry exact pending reprocessing command", exact=True).click()
        self.page.get_by_text("Only affected downstream records were invalidated", exact=False).wait_for()
        self.assertEqual(1, self.page.evaluate("window.__REPROCESSING_UI_TEST__.acceptedCount"))
        self.assertTrue(
            self.page.evaluate(
                "(()=>{const c=window.__REPROCESSING_UI_TEST__.calls.filter(c=>c.action==='accept');"
                "return c.length===2 && JSON.stringify(c[0])===JSON.stringify(c[1]);})()"
            )
        )
        self.assertFalse(self.errors)

    def test_dirty_reconciliation_guard_and_lock_suppresses_late_private_reply(self):
        self.page.get_by_role("checkbox", name=re.compile("^Document revision ")).check()
        self.page.get_by_role("button", name="Reprocess selected", exact=True).click()
        self.page.get_by_role("button", name="Compare this document", exact=True).click()
        self.page.get_by_label("Reconciliation rationale", exact=True).fill("SYNTHETIC unsaved private rationale")
        self.assertTrue(self.page.evaluate("window.__REPROCESSING_UI_TEST__.blocked"))
        self.assertFalse(
            self.page.get_by_role("button", name="Open accepted revision in Reader", exact=True).is_enabled()
        )
        self.page.get_by_role("button", name="Undo unsaved reconciliation", exact=True).click()
        self.page.evaluate("window.__REPROCESSING_UI_TEST__.hold=true")
        self.page.get_by_role("button", name="Refresh batch outcomes", exact=True).click()
        self.page.wait_for_function("window.__REPROCESSING_UI_TEST__.release !== null")
        self.page.evaluate("window.__REPROCESSING_MOUNT__(false);window.__REPROCESSING_UI_TEST__.release()")
        self.page.get_by_text(
            "Open a local project to review parsing quality and saved corrections.", exact=True
        ).wait_for()
        self.assertNotIn("SYNTHETIC", self.page.locator("body").inner_text())
        self.assertFalse(self.errors)

    def test_create_another_batch_after_inspecting_an_existing_one(self):
        self.page.get_by_role("button", name="Load retained reprocessing batches", exact=True).click()
        self.page.get_by_role("button", name=re.compile("^Inspect batch ")).click()
        self.page.get_by_role("checkbox", name=re.compile("^Document revision ")).check()
        self.page.get_by_role("button", name="Reprocess selected", exact=True).click()
        self.page.get_by_text("Batch retained. Process pending jobs", exact=False).wait_for()
        self.assertEqual(
            0, self.page.get_by_role("button", name="Retry exact pending reprocessing command", exact=True).count()
        )
        self.assertEqual(1, self.page.evaluate("window.__REPROCESSING_UI_TEST__.createdCount"))
        self.assertFalse(self.errors)

    def test_non_rematch_correction_on_reference_node_keeps_null_reference_mapping(self):
        self.page.evaluate("window.__REPROCESSING_UI_TEST__.referenceCandidate=true")
        self.ready_plan()
        mapping = self.page.evaluate(
            "window.__REPROCESSING_UI_TEST__.calls.find(c=>c.action==='reconcile').reconciliation.mappings[0]"
        )
        self.assertIsNone(mapping["referenceId"])
        self.assertFalse(self.errors)

    def test_quality_vector_regression_remains_visible_without_a_new_triage_reason(self):
        self.page.evaluate("window.__REPROCESSING_UI_TEST__.qualityRegression=true")
        self.ready_plan()
        # The retained compare before save is the relevant old/new observation.
        self.page.get_by_role("button", name="Compare this document", exact=True).click()
        prior = self.page.get_by_role("region", name="Prior quality observations", exact=True)
        candidate = self.page.get_by_role("region", name="Candidate quality observations", exact=True)
        self.assertIn("observed Count\n8", prior.inner_text())
        self.assertIn("observed Count\n3", candidate.inner_text())
        self.assertIn("missing Count\n5", candidate.inner_text())
        self.assertIn("No reasons reported", prior.inner_text())
        self.assertIn("No reasons reported", candidate.inner_text())
        self.assertFalse(self.errors)

    def test_candidate_pages_keep_selected_target_and_bounded_selector_options(self):
        self.page.evaluate("window.__REPROCESSING_UI_TEST__.largeCandidatePages=true")
        self.page.get_by_role("checkbox", name=re.compile("^Document revision ")).check()
        self.page.get_by_role("button", name="Reprocess selected", exact=True).click()
        self.page.get_by_role("button", name="Compare this document", exact=True).click()
        selected = self.page.get_by_role("combobox", name=re.compile("^Candidate target")).first
        selected.select_option(index=1)
        chosen = selected.input_value()
        for _ in range(8):
            self.page.get_by_role("button", name="Next comparison page and candidate objects", exact=True).click()
            self.assertEqual(chosen, selected.input_value())
            self.assertLessEqual(selected.locator("option").count(), 85)
        self.assertEqual(32, self.page.get_by_role("combobox", name=re.compile("^Candidate target")).count())
        self.assertFalse(self.errors)

    def test_restart_discovers_original_checkpoint_after_batch_cancel_and_exact_lost_resume(self):
        self.page.evaluate("window.__REPROCESSING_UI_TEST__.runningImpact=true")
        self.ready_plan()
        self.page.get_by_role("button", name="Approve exact reparse for this document", exact=True).click()
        self.page.get_by_role("button", name="Resume pending downstream invalidation", exact=True).wait_for()
        self.page.get_by_role("button", name="Cancel future batch work", exact=True).click()
        self.page.get_by_text("Future batch work is cancelled", exact=False).wait_for()
        self.page.evaluate("window.__REPROCESSING_MOUNT__(false)")
        self.page.get_by_text(
            "Open a local project to review parsing quality and saved corrections.", exact=True
        ).wait_for()
        self.page.evaluate("window.__REPROCESSING_MOUNT__(true)")
        self.page.get_by_role("button", name="Load retained reprocessing batches", exact=True).click()
        self.page.get_by_role("button", name=re.compile("^Inspect batch ")).click()
        self.page.get_by_role("button", name="Inspect retained downstream invalidation", exact=True).click()
        self.page.evaluate("window.__REPROCESSING_UI_TEST__.unknown=true")
        self.page.get_by_role("button", name="Resume pending downstream invalidation", exact=True).click()
        self.page.get_by_role("button", name="Retry exact pending reprocessing command", exact=True).wait_for()
        self.page.evaluate("window.__REPROCESSING_UI_TEST__.unknown=false")
        self.page.get_by_role("button", name="Retry exact pending reprocessing command", exact=True).click()
        self.page.get_by_text("completed: 64 of 64 affected records processed", exact=False).wait_for()
        self.assertEqual(1, self.page.evaluate("window.__REPROCESSING_UI_TEST__.resumedCount"))
        self.assertTrue(
            self.page.evaluate(
                "(()=>{const c=window.__REPROCESSING_UI_TEST__.calls.filter(c=>c.action==='resume-impact');"
                "return c.length===2 && JSON.stringify(c[0])===JSON.stringify(c[1]);})()"
            )
        )
        self.assertFalse(self.errors)


if __name__ == "__main__":
    unittest.main(verbosity=2)
