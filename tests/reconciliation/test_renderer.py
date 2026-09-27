"""Production React/generated client/Core interactions; browser transport is explicit."""

import functools
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

from playwright.sync_api import expect, sync_playwright
from research_observatory_core.ingestion.import_drafts import ImportPermission
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
        self.page.set_viewport_size({"width": 720, "height": 1000})
        for zoom in ("100%", "200%"):
            self.page.evaluate("zoom => document.documentElement.style.zoom = zoom", zoom)
            self.assertFalse(
                self.page.evaluate("() => document.documentElement.getBoundingClientRect().width > innerWidth + 1")
            )
            self.assertFalse(
                self.page.evaluate("() => document.documentElement.scrollWidth > document.documentElement.clientWidth")
            )
            self.assertTrue(self.page.get_by_role("button", name="Apply reviewed decision", exact=True).is_visible())
        self.page.evaluate("() => document.documentElement.style.zoom = '100%'")
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
