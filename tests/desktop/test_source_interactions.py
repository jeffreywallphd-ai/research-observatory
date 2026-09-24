"""Built renderer interactions with an explicit native/Core response double.

No native dialog, protected persistence or actual provider access is claimed.
Those boundaries have separate native/runtime integration checks.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from playwright.sync_api import expect, sync_playwright
from research_observatory_core.connectors.providers import HOSTS, capabilities

from tests.desktop import test_model_center_interactions as fixtures
from tests.desktop.test_import_visual import TEXT_COLORS, contrast_ratio, font_face_available, git

REPO = fixtures.REPO
inline_product_index = fixtures.inline_product_index
product_build_errors = fixtures.product_build_errors


class SourceInteractionTests(unittest.TestCase):
    def supporting_workflow_page(self, context: Any, document: str) -> tuple[Any, list[str]]:
        return fixtures.ModelCenterInteractionTests().supporting_workflow_page(
            context, document, fixture=self.supporting_workflow_fixture()
        )

    def open_supporting_tool(self, page: Any, name: str) -> None:
        fixtures.ModelCenterInteractionTests().open_supporting_tool(page, name)

    def supporting_workflow_fixture(self) -> str:
        base = fixtures.ModelCenterInteractionTests().supporting_workflow_fixture()
        wrapper = r"""(() => {
          const original = window.__TAURI_INTERNALS__.invoke;
          const state = window.__SOURCE_TEST__ = { requests: [], configurations: [], cancels: [],
            pending: [], uncertain: false, status: 'failed', previewDenied: false,
            submitted: false, query: null, invocationId: null, observed: false,
            intentCommands: [], currentIntent: null };
          const response = body => ({ status: 200, contentType: 'application/json',
            traceId: 'a'.repeat(32), etag: null, body: JSON.stringify(body) });
          const jobId = '01900000-0000-7000-8000-000000000031';
          window.__TAURI_INTERNALS__.invoke = async (command, args) => {
            if (command === 'core_api_request' && args.request.path === '/projects/intent') {
              const result = await original(command, args);
              const workspace = JSON.parse(result.body);
              if (state.currentIntent === null) state.currentIntent = workspace.current;
              const current = state.currentIntent;
              return response({...workspace,current,history:[{
                revision:current.revision,revisionId:current.revisionId,
                revisionContentHash:current.revisionContentHash,createdAt:current.createdAt,
                status:current.status,primaryUseCase:current.primaryUseCase,unresolvedDecisionCount:0}]});
            }
            if (command === 'core_api_request' && args.request.path.startsWith('/projects/intent/')) {
              const body = JSON.parse(args.request.body);
              state.intentCommands.push({path:args.request.path, body});
              if (args.request.path.endsWith('/preview')) return response({schemaVersion:'1.0',
                expectedRevision:body.expectedRevision,changeCategories:['egress-policy'],
                affectedWorkflows:['Research Intent'],affectedOutputs:[],affectedSchemas:['research-intent-revision'],
                affectedCheckpoints:[],autonomyDefaultEffects:[],stoppingLogicEffects:[],staleArtifactIds:[],
                allToolsAccessible:true,evidenceRequirementsUnchanged:true,provenanceRequirementsUnchanged:true,
                warnings:[],acknowledgementRequired:true,acknowledgementToken:'b'.repeat(64)});
              if (args.request.path.endsWith('/drafts')) {
                state.currentIntent = {...state.currentIntent,egressPolicy:body.egressPolicy,
                  revision:2,revisionId:'01900000-0000-7000-8000-000000000042',
                  revisionContentHash:'sha256:'+'c'.repeat(64),revisionRationale:body.revisionRationale};
                return response(state.currentIntent);
              }
              throw Error('Unexpected acceptance: source test must not grant authority');
            }
            if (command === 'configure_scholarly_source') {
              state.configurations.push(args.request);
              return new Promise(resolve => state.pending.push(resolve));
            }
            if (command === 'cancel_scholarly_source_configuration') {
              state.cancels.push(args.operationId); return;
            }
            if (command !== 'core_api_request' || !args.request.path.startsWith('/projects/connectors/'))
              return original(command, args);
            state.requests.push(args.request);
            if (args.request.path.endsWith('/capabilities')) return response(__CAPABILITIES__);
            const body = JSON.parse(args.request.body);
            const run = () => ({previewId:jobId,invocationId:state.invocationId,jobId,workflowRunId:jobId,
              providerId:'unpaywall',operation:'oa-resolution',state:state.observed?'succeeded':'failed',
              updatedAt:'2026-09-24T12:00:00.000Z',diagnosticCode:state.observed?null:'connector-provider-unavailable'});
            if (args.request.path.endsWith('/recent')) return response({items:state.submitted ? [run()] : [],
              scope:'latest-20-source-jobs-within-100-workflows'});
            if (args.request.path.endsWith('/inspect')) return response(state.submitted ? {
              job:run(),queryJson:JSON.stringify(state.query),scientificRequestSha256:'sha256:'+'a'.repeat(64),
              observation:state.observed ? {observationId:jobId,observedAt:'2026-09-24T12:00:00.000Z',
                retrievedAt:'2026-09-24T12:00:00.000Z',outcome:'complete',continuation:'exhausted',
                recordCount:2,fieldProjection:'title-oa-locations-discovery',records:[{
                  providerId:'unpaywall',rawIdentifier:{scheme:'doi',value:'10.99999/synthetic-'+body.recordOffset},
                  identifiers:[],retrievedAt:'2026-09-24T12:00:00.000Z',
                  terms:{license:{state:'reported',value:'cc-by'},terms:{state:'unknown',value:null},access:'open'},
                  fields:[{namespace:'unpaywall',name:'candidate.title',encoding:'text',
                    value:'<b>Synthetic title '+body.recordOffset+'</b>'},
                    {namespace:'unpaywall',name:'candidate.oa-locations',encoding:'json',
                      value:JSON.stringify([{url:'https://example.invalid/synthetic',hostType:'repository',license:'cc-by'}])}]
                }]} : null,recordOffset:state.observed?body.recordOffset:0,
              nextRecordOffset:state.observed && body.recordOffset===0?1:null} : null);
            if (args.request.path.endsWith('/previews')) {
              if (state.previewDenied) throw Error('synthetic policy denial');
              state.query = body.request.query; state.invocationId = body.request.invocationId;
              return response({ previewId: jobId, request: body.request, retention: body.retention,
                requestSha256: 'sha256:' + 'b'.repeat(64), destinationHost: 'api.unpaywall.org',
                terms: { license: {state:'unknown',value:null}, terms:{state:'unknown',value:null},access:'unknown'},
                intentRevisionId: jobId, intentSha256: 'sha256:' + 'c'.repeat(64),
                policySha256: 'sha256:' + 'd'.repeat(64), expiresAt:'2099-01-01T00:00:00Z',
                confirmation:'synthetic-confirmation' });
            }
            if (args.request.path.endsWith('/confirmations')) {
              state.submitted = true;
              if (state.uncertain) throw Error('synthetic lost reply');
            }
            return response({jobId, workflowRunId:jobId,
              state: args.request.path.endsWith('/confirmations') ? 'running' :
                args.request.path.endsWith('/cancel') ? 'cancelled' : state.status,
              diagnosticCode: args.request.path.endsWith('/status') ? 'connector-provider-unavailable' : null });
          };
        })();"""
        values = {"items": [capabilities(provider).model_dump(mode="json", by_alias=True) for provider in HOSTS]}
        for item in values["items"]:
            item["configuration"] = "ready"
        return base + wrapper.replace("__CAPABILITIES__", json.dumps(values))

    def open_sources(self, page: Any) -> Any:
        self.open_supporting_tool(page, "Source Manager")
        region = page.locator("[data-source-manager]")
        expect(region.get_by_role("button", name="Test Unpaywall", exact=True)).to_be_enabled()
        return region

    def preview(self, page: Any) -> None:
        page.get_by_role("button", name="Test Unpaywall", exact=True).click()
        expect(page.get_by_role("heading", name="Test unpaywall", exact=True)).to_be_focused()
        page.get_by_label("DOI to look up", exact=True).fill("10.99999/synthetic")
        preview = page.get_by_role("button", name="Preview source request", exact=True)
        expect(preview).to_be_disabled()
        page.get_by_role("checkbox", name="I have permission to store and inspect", exact=False).check()
        preview.click()
        expect(page.get_by_role("button", name="Send this DOI to unpaywall", exact=True)).to_be_visible()
        self.assertEqual([], page.evaluate("__SOURCE_TEST__.requests.filter(r => r.path.endsWith('/confirmations'))"))

    def test_built_source_journey_and_late_configuration_focus(self) -> None:
        self.assertEqual([], product_build_errors(REPO))
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                for theme in ("light", "dark"):
                    with self.subTest(theme=theme):
                        context = browser.new_context(viewport={"width": 1280, "height": 900}, reduced_motion="reduce")
                        page, errors = self.supporting_workflow_page(context, inline_product_index(REPO))
                        if theme == "dark":
                            page.locator("[data-theme-toggle]").click()
                        region = self.open_sources(page)
                        self.assertEqual(0, region.locator('input[type="password"],input[type="email"]').count())
                        region.get_by_role("button", name="Configure Unpaywall", exact=True).click()
                        page.wait_for_function("__SOURCE_TEST__.configurations.length === 1")
                        command = page.evaluate("__SOURCE_TEST__.configurations[0]")
                        self.assertEqual({"root", "projectId", "providerId", "operationId"}, set(command))
                        self.open_supporting_tool(page, "Application settings")
                        page.wait_for_function("__SOURCE_TEST__.cancels.length === 1")
                        self.assertEqual([command["operationId"]], page.evaluate("__SOURCE_TEST__.cancels"))
                        self.open_supporting_tool(page, "Source Manager")
                        sentinel = page.locator("[data-theme-toggle]")
                        sentinel.focus()
                        page.evaluate("__SOURCE_TEST__.pending[0]({status:'saved'})")
                        expect(region.get_by_role("button", name="Configure Unpaywall", exact=True)).to_be_enabled()
                        page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
                        expect(sentinel).to_be_focused()
                        self.assertNotIn("Source settings saved privately", region.inner_text())
                        region.get_by_role("button", name="Configure Unpaywall", exact=True).click()
                        page.wait_for_function("__SOURCE_TEST__.pending.length === 2")
                        page.evaluate("__SOURCE_TEST__.pending[1]({status:'cancelled'})")
                        expect(region.get_by_role("button", name="Configure Unpaywall", exact=True)).to_be_focused()
                        expect(
                            region.get_by_text("Configuration cancelled before saving.", exact=False)
                        ).to_be_visible()
                        self.preview(page)
                        page.get_by_role("button", name="Send this DOI to unpaywall", exact=True).click()
                        expect(page.get_by_text("Request running", exact=True)).to_be_visible()
                        page.get_by_role("button", name="Refresh request status", exact=True).click()
                        expect(
                            page.get_by_text("Request failed — no successful coverage implied", exact=True)
                        ).to_be_visible()
                        self.assertEqual(
                            1,
                            page.evaluate(
                                "__SOURCE_TEST__.requests.filter(r => r.path.endsWith('/confirmations')).length"
                            ),
                        )
                        page.get_by_role("button", name="Close test panel", exact=True).click()
                        expect(region.get_by_role("button", name="Test Unpaywall", exact=True)).to_be_focused()
                        page.evaluate("__SOURCE_TEST__.requests = []; __SOURCE_TEST__.uncertain = true")
                        self.preview(page)
                        page.get_by_role("button", name="Send this DOI to unpaywall", exact=True).click()
                        expect(
                            page.get_by_role("heading", name="Submission outcome unconfirmed", exact=True)
                        ).to_be_visible()
                        self.assertEqual(
                            0, page.get_by_role("button", name="Send this DOI to unpaywall", exact=True).count()
                        )
                        page.get_by_role("button", name="Inspect this source request", exact=True).click()
                        expect(page.get_by_role("heading", name="Source request history", exact=True)).to_be_focused()
                        expect(
                            page.locator("[data-source-inspection]").get_by_text("10.99999/synthetic", exact=False)
                        ).to_be_visible()
                        expect(
                            page.get_by_role("heading", name="No accepted observation yet", exact=True)
                        ).to_be_visible()
                        # Repeating the same explicit inspect must refresh its durable state.
                        page.evaluate("__SOURCE_TEST__.observed = true")
                        page.get_by_role("button", name="Inspect this source request", exact=True).click()
                        expect(page.get_by_role("heading", name="Source record 1 of 2", exact=True)).to_be_visible()
                        inspected = page.locator("[data-source-inspection]")
                        expect(inspected.get_by_text("<b>Synthetic title 0</b>", exact=True)).to_be_visible()
                        self.assertEqual(0, inspected.locator("b").count())
                        expect(inspected.get_by_text('"hostType":"repository"', exact=False)).to_be_visible()
                        expect(inspected.get_by_text("2 — not a total for the source", exact=True)).to_be_visible()
                        page.get_by_role("button", name="Next source record", exact=True).click()
                        expect(page.get_by_role("heading", name="Source record 2 of 2", exact=True)).to_be_visible()
                        page.get_by_role("button", name="Previous source record", exact=True).click()
                        expect(page.get_by_role("heading", name="Source record 1 of 2", exact=True)).to_be_visible()
                        self.assertEqual(
                            1,
                            page.evaluate(
                                "__SOURCE_TEST__.requests.filter(r => r.path.endsWith('/confirmations')).length"
                            ),
                        )
                        page.get_by_role("button", name="Close test panel", exact=True).focus()
                        page.keyboard.press("Escape")
                        expect(region.get_by_role("button", name="Test Unpaywall", exact=True)).to_be_focused()
                        self.assertEqual([], errors)
                        self.assertFalse(page.evaluate("document.documentElement.scrollWidth > innerWidth"))
                        context.close()
            finally:
                browser.close()

    def test_source_contrast_reflow_and_controlled_theme_captures(self) -> None:
        self.assertEqual([], product_build_errors(REPO))
        head = git("rev-parse", "HEAD")
        fixture = Path(tempfile.mkdtemp(prefix="source-visual-", dir=REPO / "artifacts/tmp"))
        report: dict[str, Any] = {
            "status": "RUNNING",
            "head": head,
            "workingTreeCleanAtStart": git("status", "--porcelain") == "",
            "samples": [],
            "screenshots": [],
            "rendering": {"deviceScaleFactor": 1, "locale": "en-US", "timezone": "UTC", "reducedMotion": "reduce"},
            "scope": "Built Source Manager with native/Core doubles; no native or provider proof",
        }
        document = inline_product_index(REPO)
        report["builtDocumentSha256"] = hashlib.sha256(document.encode()).hexdigest()
        visual = json.loads((REPO / "verification/extensions/desktop-ui.json").read_text("utf-8"))["visual"]
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    self.assertEqual(visual["browserVersion"], browser.version)
                    self.assertEqual(visual["playwrightVersion"], importlib.metadata.version("playwright"))
                    report.update(browser=browser.version, playwright=importlib.metadata.version("playwright"))
                    for theme in ("light", "dark"):
                        context = browser.new_context(
                            viewport={"width": 1440, "height": 900},
                            device_scale_factor=1,
                            locale="en-US",
                            timezone_id="UTC",
                            reduced_motion="reduce",
                        )
                        page, errors = self.supporting_workflow_page(context, document)
                        if theme == "dark":
                            page.locator("[data-theme-toggle]").click()
                        region = self.open_sources(page)
                        expect(page.locator("html")).to_have_attribute("data-theme", theme)
                        report["fonts"] = {font: font_face_available(page, font) for font in visual["requiredFonts"]}
                        self.assertTrue(all(report["fonts"].values()))
                        for state in ("inventory", "inspection"):
                            if state == "inspection":
                                self.preview(page)
                                page.evaluate("__SOURCE_TEST__.uncertain = true")
                                page.get_by_role("button", name="Send this DOI to unpaywall", exact=True).click()
                                expect(
                                    page.get_by_role("heading", name="Submission outcome unconfirmed", exact=True)
                                ).to_be_visible()
                                page.evaluate("__SOURCE_TEST__.observed = true")
                                page.get_by_role("button", name="Inspect this source request", exact=True).click()
                                expect(
                                    page.get_by_role("heading", name="Source record 1 of 2", exact=True)
                                ).to_be_visible()
                            for width, height in ((1440, 900), (1280, 720), (720, 450)):
                                page.set_viewport_size({"width": width, "height": height})
                                page.evaluate("() => document.fonts.ready")
                                geometry = region.evaluate("""el => ({
                                  viewport: document.documentElement.clientWidth,
                                  document: document.documentElement.scrollWidth,
                                  left: el.getBoundingClientRect().left,
                                  right: el.getBoundingClientRect().right})""")
                                self.assertLessEqual(geometry["document"], geometry["viewport"] + 1)
                                self.assertGreaterEqual(geometry["left"], 0)
                                self.assertLessEqual(geometry["right"], geometry["viewport"] + 1)
                                colors = region.evaluate(TEXT_COLORS)
                                self.assertGreater(len(colors), 30)
                                for color in colors:
                                    color["ratio"] = contrast_ratio(color["foreground"], color["background"])
                                report["samples"].append(
                                    {
                                        "state": state,
                                        "theme": theme,
                                        "width": width,
                                        "height": height,
                                        "geometry": geometry,
                                        "textColors": colors,
                                    }
                                )
                                self.assertTrue(
                                    all(color["ratio"] >= color["minimum"] for color in colors),
                                    [color for color in colors if color["ratio"] < color["minimum"]],
                                )
                                target = region if state == "inventory" else page.locator("[data-source-inspection]")
                                capture = fixture / f"{state}-{theme}-{width}.png"
                                target.screenshot(path=str(capture), animations="disabled")
                                report["screenshots"].append(
                                    {
                                        "path": capture.relative_to(REPO).as_posix(),
                                        "sha256": hashlib.sha256(capture.read_bytes()).hexdigest(),
                                    }
                                )
                        self.assertEqual([], errors)
                        context.close()
                finally:
                    browser.close()
            self.assertEqual(head, git("rev-parse", "HEAD"))
            report["status"] = "PASS"
        except BaseException as error:
            report.update(status="FAIL", failureType=type(error).__name__)
            raise
        finally:
            (fixture / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(
                json.dumps(
                    {"report": (fixture / "result.json").relative_to(REPO).as_posix(), "status": report["status"]}
                )
            )

    def test_intent_egress_requires_explicit_destinations_and_fresh_impact(self) -> None:
        self.assertEqual([], product_build_errors(REPO))
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            try:
                page, errors = self.supporting_workflow_page(context, inline_product_index(REPO))
                self.open_supporting_tool(page, "Research intent")
                mode = page.get_by_label("Data allowed to leave this computer", exact=True)
                expect(mode).to_have_value("local-only")
                destination = page.get_by_role("checkbox", name="Allow requests to Unpaywall", exact=True)
                expect(destination).not_to_be_checked()
                expect(destination).to_be_disabled()
                mode.select_option("approved-content")
                preview = page.get_by_role("button", name="Preview revision effects", exact=True)
                expect(preview).to_be_disabled()
                expect(page.get_by_role("button", name="Save draft revision", exact=True)).to_be_disabled()
                destination.check()
                preview.click()
                acknowledgement = page.locator(".intent-impact input[type=checkbox]")
                expect(acknowledgement).to_be_visible()
                acknowledgement.check()
                page.get_by_role("checkbox", name="Allow requests to Crossref", exact=True).check()
                expect(acknowledgement).to_have_count(0)
                preview.click()
                acknowledgement.check()
                page.get_by_label("Revision rationale", exact=True).fill(
                    "Allow only explicit synthetic source requests."
                )
                page.get_by_role("button", name="Save draft revision", exact=True).click()
                expect(page.get_by_text("Revision 2 · decision complete draft", exact=True)).to_be_visible()
                calls = page.evaluate("__SOURCE_TEST__.intentCommands")
                self.assertEqual(
                    ["/projects/intent/preview", "/projects/intent/preview", "/projects/intent/drafts"],
                    [item["path"] for item in calls],
                )
                expected = {"mode": "approved-content", "approvedDestinationIds": ["unpaywall", "crossref"]}
                self.assertEqual(expected, calls[-1]["body"]["egressPolicy"])
                self.assertEqual("b" * 64, calls[-1]["body"]["impactAcknowledgement"])
                self.assertEqual(
                    {"mode": "approved-content", "approvedDestinationIds": ["unpaywall"]},
                    calls[0]["body"]["egressPolicy"],
                )
                expect(page.get_by_role("button", name="Accept intent revision", exact=True)).to_be_disabled()
                mode.select_option("local-only")
                expect(destination).not_to_be_checked()
                expect(page.get_by_role("checkbox", name="Allow requests to Crossref", exact=True)).not_to_be_checked()
                self.assertEqual([], errors)
            finally:
                context.close()
                browser.close()


if __name__ == "__main__":
    unittest.main()
