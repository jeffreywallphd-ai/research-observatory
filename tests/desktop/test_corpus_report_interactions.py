"""Built Corpus Canvas renderer interaction against a controlled Core response port.

The authenticated Core/protected-store boundary is covered separately. This test
checks the production React controls, generated client, focus, and recovery path.
"""

from __future__ import annotations

import json
import unittest
from playwright.sync_api import expect, sync_playwright

from tests.desktop import test_model_center_interactions as fixtures


REPO = fixtures.REPO
inline_product_index = fixtures.inline_product_index
product_build_errors = fixtures.product_build_errors


PROJECT_ID = "11111111-1111-4111-8111-111111111111"
PROJECT_ROOT = "C:/Research/study-one"
PROTECTED_LABEL = "Synthetic protected corpus record"


class CorpusReportInteractionTests(unittest.TestCase):
    def report_fixture(self) -> tuple[dict, dict]:
        source = REPO / "packages/contracts/corpus-reports/fixtures"
        snapshot = json.loads((source / "valid-snapshot.v1.json").read_text("utf-8"))
        drill = json.loads((source / "valid-drill-page.v1.json").read_text("utf-8"))
        snapshot["projectId"] = PROJECT_ID
        drill["projectId"] = PROJECT_ID
        drill["members"][0]["projectId"] = PROJECT_ID
        drill["members"][0]["displayLabel"] = PROTECTED_LABEL
        return snapshot, drill

    def browser_fixture(self, snapshot: dict, drill: dict) -> str:
        base = fixtures.ModelCenterInteractionTests().supporting_workflow_fixture()
        report_port = r"""(() => {
          const original = window.__TAURI_INTERNALS__.invoke;
          const snapshot = __SNAPSHOT__;
          const drill = __DRILL__;
          const traceId = '0123456789abcdef0123456789abcdef';
          const state = window.__CORPUS_TEST__ = {requests: [], denyDrill: false};
          const success = body => ({status: 200, contentType: 'application/json', traceId,
            etag: null, body: JSON.stringify(body)});
          const denied = () => ({status: 403, contentType: 'application/problem+json',
            traceId, etag: null, body: JSON.stringify({
              type: 'urn:research-observatory:problem:access-denied',
              title: 'Report access denied', status: 403,
              detail: 'Report inspection is denied for this project.',
              code: 'RO-CORE-ACCESS-DENIED', traceId, retryable: false,
              remediation: 'Reopen the snapshot after checking current access.'
            })});
          window.__TAURI_INTERNALS__.invoke = async (command, args) => {
            const request = args?.request;
            if (command !== 'core_api_request'
              || !request?.path?.startsWith('/projects/corpus/reports/')) {
              return original(command, args);
            }
            const body = JSON.parse(request.body);
            state.requests.push({method: request.method, path: request.path, body});
            if (request.path === '/projects/corpus/reports/inspect') return success(snapshot);
            if (request.path === '/projects/corpus/reports/drill') {
              return state.denyDrill ? denied() : success({...drill, filter: body.filter});
            }
            throw Error('Unexpected corpus report mutation');
          };
        })();"""
        return base + report_port.replace("__SNAPSHOT__", json.dumps(snapshot)).replace("__DRILL__", json.dumps(drill))

    def test_aggregate_keyboard_drill_denial_and_visible_recovery(self) -> None:
        self.assertEqual([], product_build_errors(REPO))
        snapshot, drill = self.report_fixture()
        source_key = snapshot["sourceContributions"][0]["sourceKey"]
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900}, reduced_motion="reduce")
            try:
                fixture = fixtures.ModelCenterInteractionTests()
                page, errors = fixture.supporting_workflow_page(
                    context, inline_product_index(REPO), fixture=self.browser_fixture(snapshot, drill)
                )
                fixture.open_supporting_tool(page, "Corpus Canvas")
                workspace = page.locator("[data-corpus-canvas]")
                workspace.wait_for()
                workspace.get_by_label("Open saved report by snapshot ID").fill(snapshot["snapshotId"])
                workspace.get_by_role("button", name="Open saved report", exact=True).click()
                expect(workspace.get_by_role("heading", name="Record drill: All canonical items")).to_be_visible()
                expect(workspace.get_by_role("button", name=f"Inspect source {source_key}")).to_be_visible()

                source_button = workspace.get_by_role("button", name=f"Inspect source {source_key}")
                source_button.focus()
                page.keyboard.press("Enter")
                selected_heading = workspace.get_by_role("heading", name=f"Record drill: Source {source_key}")
                expect(selected_heading).to_be_focused()
                expect(workspace.get_by_role("row", name=f"{PROTECTED_LABEL} candidate 2 Inspect record")).to_be_visible()
                expect(page.locator("[data-live-region]")).to_contain_text(
                    f"Source {source_key}: 1 canonical item in this saved report. Page 1 loaded."
                )
                calls = page.evaluate("window.__CORPUS_TEST__.requests")
                expected_filter = {**drill["filter"], "kind": "source", "sourceKey": source_key}
                self.assertEqual("POST", calls[2]["method"])
                self.assertEqual("/projects/corpus/reports/drill", calls[2]["path"])
                self.assertEqual({
                    "root": PROJECT_ROOT, "snapshotId": snapshot["snapshotId"],
                    "filter": expected_filter, "cursor": None, "limit": 50,
                }, calls[2]["body"])

                workspace.get_by_role("button", name=f"Inspect record {PROTECTED_LABEL}").click()
                expect(workspace.get_by_role("heading", name=PROTECTED_LABEL)).to_be_focused()
                self.assertIn(drill["members"][0]["itemRevisionId"], workspace.inner_text())

                page.evaluate("window.__CORPUS_TEST__.denyDrill = true")
                workspace.get_by_role("button", name="Inspect Year known items: 1").click()
                expect(workspace.get_by_text("Corpus report inaccessible", exact=True)).to_be_visible()
                expect(workspace.locator(".corpus-empty")).to_be_visible()
                open_button = workspace.get_by_role("button", name="Open saved report", exact=True)
                expect(open_button).to_be_focused()
                self.assertNotIn(PROTECTED_LABEL, workspace.inner_html())
                self.assertNotIn(drill["members"][0]["itemRevisionId"], workspace.inner_html())
                self.assertNotIn(PROTECTED_LABEL, page.evaluate("JSON.stringify(localStorage)"))
                calls = page.evaluate("window.__CORPUS_TEST__.requests")
                self.assertEqual("coverage", calls[3]["body"]["filter"]["kind"])
                self.assertEqual("year", calls[3]["body"]["filter"]["dimension"])
                self.assertEqual("known", calls[3]["body"]["filter"]["state"])

                page.evaluate("window.__CORPUS_TEST__.denyDrill = false")
                open_button.click()
                expect(workspace.get_by_role("heading", name="Record drill: All canonical items")).to_be_visible()
                expect(workspace.get_by_role("button", name=f"Inspect record {PROTECTED_LABEL}")).to_be_visible()
                calls = page.evaluate("window.__CORPUS_TEST__.requests")
                self.assertEqual("/projects/corpus/reports/inspect", calls[4]["path"])
                self.assertEqual({"root": PROJECT_ROOT, "snapshotId": snapshot["snapshotId"]}, calls[4]["body"])
                self.assertEqual("all", calls[5]["body"]["filter"]["kind"])
                self.assertEqual([], errors)
            finally:
                context.close()
                browser.close()
