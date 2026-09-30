"""Production React/generated client/Core interactions; browser transport is explicit."""

import functools
import json
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

from playwright.sync_api import expect, sync_playwright
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.ingestion.import_drafts import ImportPermission, ImportRights
from research_observatory_core.ports.import_previews import PreviewDraftChange

from tests.reconciliation import test_batch_worker as fixtures

REPO = Path(__file__).resolve().parents[2]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


class RendererHarness(unittest.TestCase):
    directory: ClassVar[tempfile.TemporaryDirectory[str]]
    output: ClassVar[Path]
    server: ClassVar[ThreadingHTTPServer]

    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix="reconciliation-renderer-", dir=REPO / "artifacts/tmp")
        cls.addClassCleanup(cls.directory.cleanup)
        cls.output = Path(cls.directory.name)
        bundled = REPO / ".local/toolchains/node-v24.19.0-win-x64/node.exe"
        node = str(bundled) if bundled.exists() else shutil.which("node") or "node"
        result = subprocess.run(
            [node, "tests/reconciliation/build-renderer.mjs", str(cls.output)],
            cwd=REPO,
            text=True,
            capture_output=True,
            timeout=60,
        )
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        cls.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(cls.output / "dist"))
        )
        cls.addClassCleanup(cls.server.server_close)
        cls.addClassCleanup(cls.server.shutdown)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()


class VersionRendererTests(RendererHarness):
    """Actual renderer and Core; the Python transport is an explicit test double."""

    def setUp(self):
        self.fixture = fixtures.BatchWorkerTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.client = self.enterContext(self.fixture.client())
        request = self.fixture.service.prepare_batch(self.fixture.root, trace_id="a" * 32)
        self.fixture.service.schedule_batch(self.fixture.root, request, trace_id="a" * 32)
        self.fixture.service.run_pending()
        self.playwright = self.enterContext(sync_playwright())
        self.browser = self.playwright.chromium.launch(headless=True)
        self.addCleanup(self.browser.close)
        self.page = self.browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        self.page.set_default_timeout(5000)
        self.replies: list[tuple[str, int, str]] = []
        self.page.expose_function("coreExchange", self.exchange)
        self.page.goto(f"http://127.0.0.1:{self.server.server_port}/")
        self.page.evaluate(
            "project => window.mount(project)", {"root": self.fixture.root, "projectId": self.fixture.f.project_id}
        )

    def exchange(self, request):
        response = self.client.request(
            request["method"],
            request["path"],
            content=request["body"],
            headers={"Content-Type": "application/json", "X-Trace-Id": "a" * 32},
        )
        self.replies.append(
            (request["path"], response.status_code, response.text if response.status_code >= 400 else "success")
        )
        return {
            "status": response.status_code,
            "contentType": response.headers["content-type"],
            "traceId": response.headers["x-trace-id"],
            "etag": response.headers.get("etag"),
            "body": response.text,
        }

    def open_versions(self):
        self.page.get_by_role("button", name="Open Work versions", exact=True).click()
        self.page.get_by_role("checkbox", name="Select Work", exact=False).first.check()
        self.page.get_by_role("button", name="Review selected Work versions", exact=True).click()
        expect(self.page.get_by_role("heading", name="Review Work versions", exact=True)).to_be_focused()

    def apply(self, rationale):
        self.page.get_by_label("Version decision rationale", exact=True).fill(rationale)
        self.page.get_by_role("button", name="Preview version decision", exact=True).click()
        expect(self.page.get_by_role("heading", name="Version decision preview", exact=True)).to_be_focused()
        self.page.get_by_role("button", name="Apply version decision", exact=True).click()
        expect(self.page.get_by_role("heading", name="Version decision saved", exact=True)).to_be_focused()
        self.page.get_by_role("button", name="Review updated versions", exact=True).click()

    def register(self, kind):
        self.page.get_by_label("Version action", exact=True).select_option("register")
        self.page.get_by_label("Version kind", exact=True).select_option(kind)
        self.page.get_by_role("checkbox", name="Version source:", exact=False).first.check()
        self.apply("Synthetic explicit version classification.")

    def test_versions_preference_warning_retry_and_retained_history(self):
        self.open_versions()
        expect(self.page.get_by_text("No preferred citable version recorded.", exact=True)).to_be_visible()
        self.register("version-of-record")
        self.page.get_by_label("Version action", exact=True).select_option("prefer")
        self.page.get_by_label("Selected version", exact=True).select_option(index=1)
        self.apply("Synthetic preferred citable version.")
        expect(self.page.get_by_text("Preferred citable version · current", exact=True)).to_be_visible()
        self.register("retraction")
        self.page.get_by_label("Version action", exact=True).select_option("relate")
        self.page.get_by_label("Relationship", exact=True).select_option("retracts")
        self.page.get_by_label("From version", exact=True).select_option(label="Retraction · version 2")
        self.page.get_by_label("To version", exact=True).select_option(label="Version of record · version 1")
        self.page.get_by_label("Retained source evidence", exact=True).select_option(index=1)
        self.page.get_by_label("Version decision rationale", exact=True).fill("Synthetic sourced retraction.")
        self.page.get_by_role("button", name="Preview version decision", exact=True).click()
        self.page.evaluate("() => { window.flags.dropVersionCommit = true; }")
        self.page.get_by_role("button", name="Apply version decision", exact=True).click()
        expect(self.page.get_by_role("button", name="Back to Works", exact=True)).to_be_disabled()
        self.page.keyboard.press("Escape")
        self.page.get_by_role("button", name="Retry same version decision", exact=True).click()
        self.page.get_by_role("button", name="Review updated versions", exact=True).click()
        expect(self.page.get_by_text("Retraction linked", exact=True)).to_be_visible()
        expect(self.page.get_by_text("Preferred citable version · requires review", exact=True)).to_be_visible()
        bodies = self.page.evaluate(
            "() => window.requests.filter(r => r.path.endsWith('versions/commit')).map(r => r.body)"
        )
        self.assertEqual(bodies[-2], bodies[-1])
        self.assertEqual(2, self.page.get_by_role("table", name="Current Work versions").locator("tbody tr").count())
        self.page.get_by_role("button", name="Inspect version history", exact=True).first.click()
        expect(self.page.get_by_role("heading", name="Retained version revision", exact=True)).to_be_visible()
        self.page.evaluate("() => window.clearProtectedState()")
        expect(self.page.get_by_text("Retraction linked", exact=True)).to_have_count(0)

    def test_version_keyboard_themes_cancel_and_recoverable_draft(self):
        for theme in ("light", "dark"):
            with self.subTest(theme=theme):
                self.page.locator("html").evaluate("(element, theme) => element.dataset.theme = theme", theme)
                self.open_versions()
                self.page.get_by_label("Version decision rationale", exact=True).fill("Keep this synthetic draft.")
                self.page.get_by_label("Version kind", exact=True).select_option("preprint")
                self.page.get_by_role("checkbox", name="Version source:", exact=False).first.check()
                self.page.evaluate("() => { window.flags.failVersionPreview = true; }")
                self.page.get_by_role("button", name="Preview version decision", exact=True).click()
                expect(self.page.get_by_label("Version decision rationale", exact=True)).to_have_value(
                    "Keep this synthetic draft."
                )
                self.page.evaluate("() => { window.flags.failVersionPreview = false; }")
                self.page.get_by_role("button", name="Preview version decision", exact=True).click()
                expect(self.page.get_by_role("heading", name="Version decision preview", exact=True)).to_be_focused()
                self.page.keyboard.press("Escape")
                expect(self.page.get_by_role("button", name="Preview version decision", exact=True)).to_be_focused()
                self.page.keyboard.press("Shift+Tab")
                expect(self.page.get_by_label("Version decision rationale", exact=True)).to_be_focused()
                self.page.keyboard.press("Tab")
                expect(self.page.get_by_role("button", name="Preview version decision", exact=True)).to_be_focused()
                self.assertNotEqual(
                    "none", self.page.evaluate("() => getComputedStyle(document.activeElement).outlineStyle")
                )
                self.page.keyboard.press("Escape")
                expect(
                    self.page.get_by_role("button", name="Review selected Work versions", exact=True)
                ).to_be_focused()
                self.page.get_by_role("button", name="Close Work versions", exact=True).click()
                expect(self.page.get_by_role("button", name="Open Work versions", exact=True)).to_be_focused()

    def test_stale_commit_refresh_preserves_draft_and_requires_new_preview(self):
        self.open_versions()
        self.page.get_by_label("Version kind", exact=True).select_option("preprint")
        self.page.get_by_role("checkbox", name="Version source:", exact=False).first.check()
        self.page.get_by_label("Reported date precision", exact=True).select_option("month")
        self.page.get_by_label("Reported date (YYYY-MM)", exact=True).fill("2025-02")
        self.page.get_by_label("Version decision rationale", exact=True).fill("Retain this synthetic draft.")
        self.page.get_by_role("button", name="Preview version decision", exact=True).click()
        expect(self.page.get_by_role("heading", name="Version decision preview", exact=True)).to_be_focused()
        body = json.loads(
            self.page.evaluate("() => window.requests.find(r => r.path.endsWith('versions/preview')).body")
        )
        body["plan"]["rationale"] = "Synthetic competing classification."
        preview = self.client.post("/projects/reconciliation/versions/preview", json=body)
        self.assertEqual(200, preview.status_code, preview.text)
        saved = self.client.post(
            "/projects/reconciliation/versions/commit",
            json={
                "root": self.fixture.root,
                "command": {
                    "commandId": preview.json()["commandId"],
                    "plan": body["plan"],
                    "expectedPreviewSha256": preview.json()["previewSha256"],
                },
            },
        )
        self.assertEqual(200, saved.status_code, saved.text)
        self.page.get_by_role("button", name="Apply version decision", exact=True).click()
        expect(
            self.page.get_by_text(
                "This decision was not applied because its evidence changed. "
                "Refresh version evidence, then prepare a new preview.",
                exact=True,
            )
        ).to_be_visible()
        expect(self.page.get_by_role("button", name="Back to Works", exact=True)).to_be_enabled()
        refresh = self.page.get_by_role("button", name="Refresh version evidence", exact=True)
        expect(refresh).to_be_focused()
        expect(self.page.get_by_role("button", name="Preview version decision", exact=True)).to_be_disabled()
        refresh.click()
        expect(self.page.get_by_role("heading", name="Review Work versions", exact=True)).to_be_focused()
        expect(self.page.get_by_label("Version kind", exact=True)).to_have_value("preprint")
        expect(self.page.get_by_label("Reported date precision", exact=True)).to_have_value("month")
        expect(self.page.get_by_label("Reported date (YYYY-MM)", exact=True)).to_have_value("2025-02")
        expect(self.page.get_by_label("Version decision rationale", exact=True)).to_have_value(
            "Retain this synthetic draft."
        )
        expect(self.page.get_by_role("checkbox", name="Version source:", exact=False).first).to_be_checked()
        self.apply("Retain this synthetic draft.")
        expect(self.page.get_by_role("table", name="Current Work versions").locator("tbody tr")).to_have_count(2)
        self.page.get_by_role("button", name="Back to Works", exact=True).click()
        self.page.get_by_role("button", name="Clear Work selection", exact=True).click()
        expect(self.page.get_by_role("button", name="Review selected Work versions", exact=True)).to_be_disabled()
        expect(self.page.get_by_role("checkbox", name="Select Work", exact=False).first).not_to_be_checked()

    def test_ambiguous_conflict_keeps_exact_command_after_actual_publication(self):
        self.open_versions()
        self.page.get_by_role("checkbox", name="Version source:", exact=False).first.check()
        self.page.get_by_label("Version decision rationale", exact=True).fill("Synthetic ambiguous reply.")
        self.page.get_by_role("button", name="Preview version decision", exact=True).click()
        expect(self.page.get_by_role("heading", name="Version decision preview", exact=True)).to_be_focused()
        self.page.evaluate("() => { window.flags.conflictVersionCommit = true; }")
        self.page.get_by_role("button", name="Apply version decision", exact=True).click()
        retry = self.page.get_by_role("button", name="Retry same version decision", exact=True)
        expect(retry).to_be_enabled()
        expect(self.page.get_by_role("button", name="Back to Works", exact=True)).to_be_disabled()
        expect(self.page.get_by_role("button", name="Refresh version evidence", exact=True)).to_be_disabled()
        self.page.keyboard.press("Escape")
        retry.click()
        self.page.get_by_role("button", name="Review updated versions", exact=True).click()
        expect(self.page.get_by_role("table", name="Current Work versions").locator("tbody tr")).to_have_count(1)
        bodies = self.page.evaluate(
            "() => window.requests.filter(r => r.path.endsWith('versions/commit')).map(r => r.body)"
        )
        self.assertEqual(bodies[-2], bodies[-1])
        self.assertTrue(
            any(status == 409 and "RO-CORE-RECONCILIATION-CONFLICT" in text for _, status, text in self.replies)
        )

    def test_version_denial_clears_protected_evidence_and_draft(self):
        self.open_versions()
        self.register("preprint")
        self.page.get_by_label("Version decision rationale", exact=True).fill("Protected synthetic rationale.")
        repository = self.fixture.f.adapters(Path(self.fixture.root), self.fixture.f.project_id).previews
        decisions = tuple(
            item.decision.model_copy(
                update={
                    "rights": item.decision.rights.model_copy(
                        update={"derive": ImportPermission(value="denied", basis="researcher-confirmed")}
                    )
                }
            )
            for item in repository.draft_page(self.fixture.preview, revision=2, after=0, limit=100)
            if item.decision.included
        )
        repository.revise_draft(
            self.fixture.preview,
            PreviewDraftChange(expected_revision=2, actor=self.fixture.f.service.actor("a" * 32), decisions=decisions),
        )
        self.page.get_by_role("button", name="Refresh version evidence", exact=True).click()
        expect(
            self.page.get_by_text(
                "Current project or source access was denied. "
                "Check accepted Intent and source rights before reopening evidence.",
                exact=True,
            )
        ).to_be_visible()
        expect(self.page.get_by_role("heading", name="Review Work versions", exact=True)).to_have_count(0)
        expect(self.page.get_by_label("Version decision rationale", exact=True)).to_have_count(0)
        self.assertNotIn("Synthetic duplicate", self.page.locator("body").inner_text())

    def test_version_revision_date_history_and_responsive_preview(self):
        self.open_versions()
        self.register("preprint")
        self.page.get_by_label("Version action", exact=True).select_option("revise")
        self.page.get_by_label("Selected version", exact=True).select_option(index=1)
        self.page.get_by_label("Version kind", exact=True).select_option("accepted-manuscript")
        self.page.get_by_label("Reported date precision", exact=True).select_option("month")
        self.page.get_by_label("Reported date (YYYY-MM)", exact=True).fill("2025-02")
        self.page.get_by_label("Version decision rationale", exact=True).fill("Synthetic revised manifestation date.")
        self.page.get_by_role("button", name="Preview version decision", exact=True).click()
        preview = self.page.get_by_role("region", name="Version decision preview", exact=True)
        expect(preview.get_by_text("Reported date: 2025-02 (month)", exact=True)).to_be_visible()
        for theme in ("light", "dark"):
            self.page.locator("html").evaluate("(element, theme) => element.dataset.theme = theme", theme)
            for width, scale in ((1440, 1), (720, 1), (720, 2)):
                self.page.set_viewport_size({"width": width, "height": 1000})
                self.page.evaluate("scale => document.documentElement.style.zoom = String(scale)", scale)
                self.assertFalse(
                    self.page.evaluate(
                        "() => document.documentElement.scrollWidth > document.documentElement.clientWidth"
                    )
                )
                button = preview.get_by_role("button", name="Apply version decision", exact=True)
                button.focus()
                expect(button).to_be_focused()
                self.assertTrue(button.evaluate("e => e.scrollHeight <= e.clientHeight + 1"))
            self.page.evaluate("() => document.documentElement.style.zoom = '1'")
            self.page.set_viewport_size({"width": 1440, "height": 1000})
            preview.scroll_into_view_if_needed()
            self.page.screenshot(path=str(REPO / f"artifacts/tmp/CAP-04.S03.T03.preview-{theme}.png"))
        preview.get_by_role("button", name="Apply version decision", exact=True).click()
        self.page.get_by_role("button", name="Review updated versions", exact=True).click()
        self.page.get_by_role("button", name="Inspect version history", exact=True).first.click()
        self.page.get_by_role("button", name="Inspect earlier revision", exact=True).click()
        expect(self.page.get_by_text("Preprint · Not reported", exact=True)).to_be_visible()

    def test_version_late_preview_cannot_restore_cleared_project(self):
        self.open_versions()
        self.page.get_by_role("checkbox", name="Version source:", exact=False).first.check()
        self.page.get_by_label("Version decision rationale", exact=True).fill("Synthetic delayed draft.")
        self.page.evaluate("""() => {
            const original = window.coreExchange;
            window.coreExchange = async request => {
                const reply = await original(request);
                if (request.path.endsWith('versions/preview')) {
                    await new Promise(resolve => { window.releaseVersionReply = resolve; });
                }
                return reply;
            };
        }""")
        self.page.get_by_role("button", name="Preview version decision", exact=True).click()
        self.page.wait_for_function("() => typeof window.releaseVersionReply === 'function'")
        self.page.evaluate("() => { window.clearProtectedState(); window.releaseVersionReply(); }")
        expect(self.page.get_by_role("heading", name="Version decision preview", exact=True)).to_have_count(0)
        self.page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")
        self.assertEqual("", self.page.locator("main").inner_text())


class ReconciliationRendererTests(RendererHarness):
    def setUp(self):
        self.fixture = fixtures.BatchWorkerTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.client = self.enterContext(self.fixture.client())
        self.playwright = self.enterContext(sync_playwright())
        self.browser = self.playwright.chromium.launch(headless=True)
        self.addCleanup(self.browser.close)
        self.page = self.browser.new_page(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
        self.page.set_default_timeout(5000)
        self.replies: list[tuple[str, int, str]] = []
        self.candidate_replies: list[dict] = []
        self.page.expose_function("coreExchange", self.exchange)
        self.page.goto(f"http://127.0.0.1:{self.server.server_port}/")
        self.page.evaluate(
            "project => window.mount(project)", {"root": self.fixture.root, "projectId": self.fixture.f.project_id}
        )
        self.page.get_by_role("button", name="Generate duplicate candidates", exact=True).click()
        self.page.get_by_role("button", name="Compare candidate 1", exact=True).click()
        try:
            expect(self.page.get_by_role("heading", name="Compare source assertions", exact=True)).to_be_focused()
        except AssertionError as error:
            raise AssertionError(
                f"{error}\nReplies: {self.replies}\nUI: {self.page.locator('body').inner_text()[:1600]}"
            ) from error

    def exchange(self, request):
        response = self.client.request(
            request["method"],
            request["path"],
            content=request["body"],
            headers={"Content-Type": "application/json", "X-Trace-Id": "a" * 32},
        )
        if request["path"].endswith("batches/schedule"):
            self.fixture.service.run_pending()
        self.replies.append(
            (request["path"], response.status_code, response.text if response.status_code >= 400 else "success")
        )
        if request["path"].endswith("/reconciliation/candidates") and response.status_code == 200:
            self.candidate_replies.append(response.json())
        return {
            "status": response.status_code,
            "contentType": response.headers["content-type"],
            "traceId": response.headers["x-trace-id"],
            "etag": response.headers.get("etag"),
            "body": response.text,
        }

    def prepare_split(self):
        self.page.get_by_role("checkbox").last.check()
        self.page.get_by_label("Decision rationale", exact=True).fill(
            "Synthetic researcher split preserves both source assertions."
        )
        self.page.get_by_role("button", name="Preview decision and affected objects", exact=True).click()
        expect(self.page.get_by_role("heading", name="Apply this reviewed decision", exact=True)).to_be_focused()

    def test_real_renderer_shows_stored_priority_before_higher_similarity(self):
        self.page.get_by_role("button", name="Back to candidates", exact=True).click()
        source = self.fixture.f
        preview = source.intake(b"title,doi\nSynthetic duplicates,\nSynthetic duplicates,\n")
        source.service.schedule(self.fixture.root, preview)
        source.service.run_pending()
        repository = source.adapters(Path(self.fixture.root), source.project_id).previews
        actor = source.service.actor("a" * 32)
        repository.revise_draft(preview, PreviewDraftChange(expected_revision=0, actor=actor))
        grant = ImportPermission(value="permitted", basis="researcher-confirmed")
        rights = ImportRights(store=grant, inspect=grant, derive=grant, index=grant)
        decisions = tuple(
            item.decision.model_copy(update={"rights": rights})
            for item in repository.draft_page(preview, revision=1, after=0, limit=100)
            if item.decision.included
        )
        self.assertEqual(2, len(decisions))
        repository.revise_draft(preview, PreviewDraftChange(expected_revision=1, actor=actor, decisions=decisions))
        source.service.schedule_commit(self.fixture.root, preview, revision=2, request_id=new_uuid_v7())
        source.service.run_pending()

        self.page.get_by_role("button", name="Generate duplicate candidates", exact=True).click()
        table = self.page.get_by_role("table", name="Duplicate candidates — historical comparison, current page")
        expect(table.locator("tbody tr")).to_have_count(6)
        actual = self.candidate_replies[-1]["items"]
        scores = [item["score"] for item in actual]
        self.assertTrue(any(score < later for index, score in enumerate(scores) for later in scores[index + 1 :]))
        self.assertEqual(
            scores,
            [int(value) for value in table.locator("tbody tr td:nth-child(2)").all_inner_texts()],
        )
        self.assertEqual(
            [f"Compare candidate {index}" for index in range(1, len(actual) + 1)],
            table.get_by_role("button", name="Compare candidate", exact=False).all_inner_texts(),
        )

    def test_uncertain_decision_survives_back_and_parent_refresh_then_retries_exact_command(self):
        self.prepare_split()
        self.page.evaluate("() => { window.flags.dropCommit = true; window.flags.failStatus = true; }")
        self.page.get_by_role("button", name="Apply reviewed decision", exact=True).click()
        retry = self.page.get_by_role("button", name="Retry same decision", exact=True)
        expect(retry).to_be_enabled()
        expect(self.page.get_by_role("button", name="Back to candidates", exact=True)).to_be_disabled()
        expect(self.page.get_by_role("button", name="Refresh reconciliation status", exact=True)).to_be_disabled()
        self.page.keyboard.press("Escape")
        expect(retry).to_be_visible()
        self.page.evaluate("() => { window.flags.failStatus = false; }")
        retry.click()
        expect(self.page.get_by_role("heading", name="Decision saved", exact=True)).to_be_focused()
        commands = self.page.evaluate(
            "() => window.requests.filter(r => r.path.endsWith('review/commit')).map(r => JSON.parse(r.body).command)"
        )
        self.assertEqual(2, len(commands))
        self.assertEqual(commands[0], commands[1])
        with self.fixture.queue._transaction(write=False) as connection:
            self.assertEqual(
                1, connection.execute("SELECT count(*) FROM reconciliation_review_decisions").fetchone()[0]
            )
        self.page.get_by_role("button", name="Review resulting Works or reverse the grouping", exact=True).click()
        expect(self.page.get_by_role("heading", name="Compare source assertions", exact=True)).to_be_focused()
        expect(self.page.get_by_label("Action", exact=True)).to_have_value("merge")
        self.page.get_by_role("button", name="Preview decision and affected objects", exact=True).click()
        self.page.get_by_role("button", name="Apply reviewed decision", exact=True).click()
        expect(self.page.get_by_role("heading", name="Decision saved", exact=True)).to_be_focused()
        with self.fixture.queue._transaction(write=False) as connection:
            self.assertEqual(
                2, connection.execute("SELECT count(*) FROM reconciliation_review_decisions").fetchone()[0]
            )
        self.page.get_by_role("button", name="Back to candidates", exact=True).click()
        expect(self.page.get_by_role("button", name="Compare candidate 1", exact=True)).to_be_focused()

    def test_sources_and_split_preview_identify_exact_assertions_and_scored_pair(self):
        labels = self.page.get_by_role("checkbox").evaluate_all(
            "elements => elements.map(e => e.closest('label').textContent)"
        )
        self.assertEqual(2, len(set(labels)))
        second = self.page.get_by_label("Source 2", exact=True).input_value()
        self.page.get_by_label("Source 1", exact=True).select_option(second)
        expect(
            self.page.get_by_role("table", name="Historical candidate feature contributions", exact=True)
        ).to_have_count(0)
        self.prepare_split()
        preview = self.page.get_by_role("region", name="Reconciliation decision preview", exact=True)
        expect(preview.get_by_text("Retained Work", exact=True)).to_be_visible()
        expect(preview.get_by_text("Separate Work", exact=True)).to_be_visible()
        self.assertIn(second, preview.inner_text())
        for theme in ("light", "dark"):
            self.page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
            self.page.screenshot(path=str(REPO / f"artifacts/tmp/reconciliation-review-{theme}.png"), full_page=True)
            self.assertFalse(self.page.evaluate("() => document.documentElement.scrollWidth > innerWidth"))
            self.assertGreaterEqual(
                self.page.get_by_label("Source 1", exact=True).evaluate("e => e.getBoundingClientRect().height"), 40
            )
        label = self.page.get_by_role("button", name="Back to decision", exact=True)
        text_height = (
            "e => { const r = document.createRange(); r.selectNodeContents(e); "
            "return r.getBoundingClientRect().height; }"
        )
        baseline = label.evaluate(text_height)
        for width, height in ((1440, 900), (1280, 720), (720, 1000)):
            self.page.set_viewport_size({"width": width, "height": height})
            for theme in ("light", "dark"):
                self.page.evaluate("theme => document.documentElement.dataset.theme = theme", theme)
                for scale in (1, 2):
                    self.page.evaluate("scale => document.documentElement.style.zoom = String(scale)", scale)
                    measured = label.evaluate(text_height)
                    self.assertAlmostEqual(baseline * scale, measured, delta=1)
                    self.assertFalse(
                        self.page.evaluate(
                            "() => document.documentElement.scrollWidth > document.documentElement.clientWidth"
                        )
                    )
                    for name in ("Back to decision", "Apply reviewed decision"):
                        control = self.page.get_by_role("button", name=name, exact=True)
                        control.focus()
                        expect(control).to_be_focused()
                        self.assertTrue(control.evaluate("e => e.scrollHeight <= e.clientHeight + 1"))
                    self.assertIn(second, preview.inner_text())
        self.page.evaluate("() => document.documentElement.style.zoom = '1'")
        self.page.keyboard.press("Escape")
        expect(
            self.page.get_by_role("button", name="Preview decision and affected objects", exact=True)
        ).to_be_focused()
        self.page.evaluate("() => window.clearProtectedState()")
        expect(self.page.get_by_role("heading", name="Compare source assertions", exact=True)).to_have_count(0)

    def test_review_json_arrays_preserve_strict_scalar_and_authority_denial(self):
        requests = self.page.evaluate("() => window.requests.map(r => ({path:r.path, body:JSON.parse(r.body)}))")
        body = next(item["body"] for item in requests if item["path"].endswith("review/context"))
        context_changes: tuple[dict[str, object], ...] = (
            {"workIds": [True]},
            {"workIds": {}},
            {"actorId": self.fixture.f.actor},
        )
        for change in context_changes:
            response = self.client.post("/projects/reconciliation/review/context", json={**body, **change})
            self.assertEqual(422, response.status_code)
        self.prepare_split()
        plan = self.page.evaluate(
            "() => JSON.parse(window.requests.find(r => r.path.endsWith('review/preview')).body).plan"
        )
        plan_changes: tuple[dict[str, object], ...] = (
            {"rationale": 1},
            {"partitions": {}},
            {"actorId": self.fixture.f.actor},
            {"partitions": plan["partitions"][:1]},
        )
        for change in plan_changes:
            response = self.client.post(
                "/projects/reconciliation/review/preview", json={"root": self.fixture.root, "plan": {**plan, **change}}
            )
            self.assertEqual(422, response.status_code)
        with self.fixture.queue._transaction(write=False) as connection:
            self.assertEqual(
                0, connection.execute("SELECT count(*) FROM reconciliation_review_decisions").fetchone()[0]
            )

    def test_current_source_rights_denial_clears_comparison_and_candidate_evidence(self):
        repository = self.fixture.f.adapters(Path(self.fixture.root), self.fixture.f.project_id).previews
        decisions = tuple(
            item.decision.model_copy(
                update={
                    "rights": item.decision.rights.model_copy(
                        update={"index": ImportPermission(value="denied", basis="researcher-confirmed")}
                    )
                }
            )
            for item in repository.draft_page(self.fixture.preview, revision=2, after=0, limit=100)
            if item.decision.included
        )
        repository.revise_draft(
            self.fixture.preview,
            PreviewDraftChange(
                expected_revision=2,
                actor=self.fixture.f.service.actor("a" * 32),
                decisions=decisions,
            ),
        )
        command = self.page.evaluate(
            "() => JSON.parse(window.requests.find(r => r.path.endsWith('review/context')).body)"
        )
        self.assertEqual(403, self.client.post("/projects/reconciliation/review/context", json=command).status_code)
        self.page.get_by_role("button", name="Refresh current evidence", exact=True).click()
        expect(self.page.get_by_text("Synthetic duplicate", exact=True)).to_have_count(0)
        expect(self.page.get_by_role("button", name="Compare candidate 1", exact=True)).to_have_count(0)
        with self.fixture.queue._transaction(write=False) as connection:
            self.assertEqual(
                0, connection.execute("SELECT count(*) FROM reconciliation_review_decisions").fetchone()[0]
            )
