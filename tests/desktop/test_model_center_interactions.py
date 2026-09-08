from __future__ import annotations

import ast
import json
import sys
import unittest
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "services/core-api/src"))

from desktop_app_check import (  # noqa: E402
    DIRECTORY_PICKER_FIXTURE,
    choose_fixture_directory,
    core_workflow_catalog_json,
    inline_product_index,
    product_build_errors,
)
from research_observatory_core.model_registry_contracts import (  # noqa: E402
    ModelManifest,
    ModelRegistryCatalog,
    canonical_hash,
)

from tests.ai.test_model_registry import manifest_document  # noqa: E402


class ModelCenterInteractionTests(unittest.TestCase):
    def supporting_workflow_fixture(self) -> str:
        # Reuse the exact established adapter without executing its Python owner
        # or duplicating Core-owned identities in a second authority fixture.
        module = ast.parse((REPO / "tools/desktop_app_check.py").read_text("utf-8"))
        owners = [
            node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "runtime_frame_errors"
        ]
        self.assertEqual(1, len(owners), "Established runtime fixture owner changed")
        assignments = [
            node
            for node in ast.walk(owners[0])
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "project_adapter"
        ]
        self.assertEqual(1, len(assignments), "Established project adapter assignment changed")
        expression = assignments[0].value
        self.assertIsInstance(expression, ast.Call)
        assert isinstance(expression, ast.Call)
        self.assertIsInstance(expression.func, ast.Attribute)
        assert isinstance(expression.func, ast.Attribute)
        self.assertEqual("replace", expression.func.attr)
        self.assertEqual([], expression.keywords)
        self.assertEqual(2, len(expression.args))
        self.assertEqual("__WORKFLOW_CATALOG__", ast.literal_eval(expression.args[0]))
        self.assertIsInstance(expression.args[1], ast.Name)
        assert isinstance(expression.args[1], ast.Name)
        self.assertEqual("workflow_catalog_json", expression.args[1].id)
        self.assertIsInstance(expression.func.value, ast.Constant)
        assert isinstance(expression.func.value, ast.Constant)
        literal = expression.func.value.value
        self.assertIsInstance(literal, str)
        assert isinstance(literal, str)
        self.assertEqual(1, literal.count("__WORKFLOW_CATALOG__"))
        wrapper = r"""(() => {
          const original = window.__TAURI_INTERNALS__.invoke;
          const state = window.__SUPPORTING_TEST__ = {
            delay: false, commands: [], pending: [], settled: []
          };
          window.__TAURI_INTERNALS__.invoke = async (command, args) => {
            if (command !== 'core_api_request'
              || args.request.path !== '/projects/workflow-progress/commands') {
              return original(command, args);
            }
            const body = JSON.parse(args.request.body);
            state.commands.push(body);
            const response = await original(command, args);
            if (!state.delay || body.action !== 'open-supporting'
              || body.supportingPageContractId !== 'model-center.html') return response;
            return new Promise((resolve, reject) => {
              const index = state.pending.length;
              state.pending.push({
                resolve: () => { state.settled.push(index); resolve(response); },
                reject: () => { state.settled.push(index); reject(Error('obsolete handoff failure')); }
              });
            });
          };
        })();"""
        return (
            literal.replace("__WORKFLOW_CATALOG__", core_workflow_catalog_json(REPO))
            + DIRECTORY_PICKER_FIXTURE
            + wrapper
        )

    def supporting_workflow_page(self, context: Any, document: str) -> tuple[Any, list[str]]:
        def route_application(route: Any) -> None:
            if route.request.url in {"http://tauri.localhost/", "http://tauri.localhost/index.html"}:
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=document)
            else:
                route.abort()

        context.route("**/*", route_application)
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.add_init_script(self.supporting_workflow_fixture())
        page.goto("http://tauri.localhost/index.html", wait_until="load")
        page.wait_for_function("document.body.dataset.applicationReady === 'true'", timeout=5000)
        self.open_supporting_tool(page, "Local projects")
        choose_fixture_directory(page, "project-root", "C:/Research/study-one")
        page.get_by_role("button", name="Open project", exact=True).click()
        page.get_by_text("Exclusive local session open", exact=True).wait_for(timeout=5000)
        page.locator("[data-workflow-nav]").wait_for(timeout=5000)
        return page, errors

    def open_supporting_tool(self, page: Any, name: str) -> None:
        menu = page.locator("[data-all-tools]")
        if menu.get_attribute("open") is None:
            menu.locator("summary").click()
        menu.get_by_role("button", name=name, exact=True).click()

    def settle_supporting_request(self, page: Any, index: int, outcome: str = "resolve") -> None:
        page.evaluate("([index, outcome]) => window.__SUPPORTING_TEST__.pending[index][outcome]()", [index, outcome])
        page.wait_for_function("index => window.__SUPPORTING_TEST__.settled.includes(index)", arg=index)
        page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")

    def assert_supporting_pending(self, page: Any) -> None:
        context = page.locator("[data-workflow-context]")
        self.assertIn("Preparing supporting-tool return", context.inner_text())
        self.assertNotIn("Supporting context expired", context.inner_text())
        self.assertEqual(0, context.get_by_role("button", name="Return to current step", exact=False).count())
        self.assertNotIn("obsolete handoff failure", page.locator("body").inner_text())
        self.assertNotIn("The workflow action did not complete", page.locator("body").inner_text())

    def test_supporting_not_started_guidance_preserves_explicit_start_and_exact_return(self) -> None:
        self.assertEqual([], product_build_errors(REPO))
        document = inline_product_index(REPO)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 720}, reduced_motion="reduce")
            try:
                page, errors = self.supporting_workflow_page(context, document)
                self.open_supporting_tool(page, "Research intent")
                self.open_supporting_tool(page, "Model & Privacy Center")
                for _theme in ("light", "dark"):
                    supporting = page.locator("[data-supporting-tool]")
                    self.assertIn("Guided workflow not started", supporting.inner_text())
                    self.assertNotIn("Supporting context expired", supporting.inner_text())
                    self.assertEqual(
                        0, supporting.get_by_role("button", name="Return to current step", exact=False).count()
                    )
                    page.locator("[data-theme-toggle]").click()
                self.assertEqual([], page.evaluate("window.__SUPPORTING_TEST__.commands"))
                page.locator("[data-workflow-stage-key='intent-contract-1'] button").click()
                self.open_supporting_tool(page, "Model & Privacy Center")
                self.assertIn("Guided workflow not started", page.locator("[data-supporting-tool]").inner_text())
                self.assertEqual([], page.evaluate("window.__SUPPORTING_TEST__.commands"))
                home = page.get_by_role("button", name="Open Project Home", exact=True)
                home.focus()
                page.keyboard.press("Enter")
                page.get_by_role("button", name="Start guided workflow", exact=True).wait_for(timeout=5000)
                self.assertEqual(0, page.get_by_role("button", name="Open Project Home", exact=True).count())
                self.assertEqual([], page.evaluate("window.__SUPPORTING_TEST__.commands"))
                page.get_by_role("button", name="Start guided workflow", exact=True).click()
                page.wait_for_function("window.__SUPPORTING_TEST__.commands.some(item => item.action === 'start')")
                page.locator("[data-supporting-tool]").wait_for(state="detached", timeout=5000)
                self.open_supporting_tool(page, "Model & Privacy Center")
                return_action = page.get_by_role("button", name="Return to current step · Research Intent", exact=True)
                return_action.wait_for(timeout=5000)
                return_action.focus()
                page.keyboard.press("Enter")
                self.assertEqual(0, page.locator("[data-supporting-tool]").count())
                self.assertEqual(
                    "step",
                    page.locator("[data-workflow-stage-key='intent-contract-1'] button").get_attribute("aria-current"),
                )
                commands = page.evaluate("window.__SUPPORTING_TEST__.commands")
                self.assertEqual(["start", "open-supporting"], [item["action"] for item in commands])
                self.assertEqual([], commands[0]["completionEvidenceRevisionIds"])
                self.assertEqual([], errors)
            finally:
                context.close()
                browser.close()

    def test_supporting_pending_requests_deny_obsolete_success_error_and_cleanup(self) -> None:
        self.assertEqual([], product_build_errors(REPO))
        document = inline_product_index(REPO)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 720}, reduced_motion="reduce")
            try:
                page, errors = self.supporting_workflow_page(context, document)
                self.open_supporting_tool(page, "Project home")
                page.get_by_role("button", name="Start guided workflow", exact=True).click()
                page.locator("[data-supporting-tool]").wait_for(state="detached", timeout=5000)
                page.evaluate("window.__SUPPORTING_TEST__.delay = true")
                for outcome in ("resolve", "reject"):
                    first = page.evaluate("window.__SUPPORTING_TEST__.pending.length")
                    self.open_supporting_tool(page, "Model & Privacy Center")
                    page.wait_for_function(
                        "count => window.__SUPPORTING_TEST__.pending.length === count", arg=first + 1
                    )
                    self.assert_supporting_pending(page)
                    page.locator("[data-workflow-stage-key='intent-contract-1'] button").click()
                    self.open_supporting_tool(page, "Model & Privacy Center")
                    page.wait_for_function(
                        "count => window.__SUPPORTING_TEST__.pending.length === count", arg=first + 2
                    )
                    self.settle_supporting_request(page, first, outcome)
                    self.assert_supporting_pending(page)
                    self.settle_supporting_request(page, first + 1)
                    return_action = page.get_by_role(
                        "button", name="Return to current step · Research Intent", exact=True
                    )
                    return_action.wait_for(timeout=5000)
                    return_action.click()
                    self.assertEqual(0, page.locator("[data-supporting-tool]").count())
                    page.locator("[data-theme-toggle]").click()
                first = page.evaluate("window.__SUPPORTING_TEST__.pending.length")
                self.open_supporting_tool(page, "Model & Privacy Center")
                page.wait_for_function("count => window.__SUPPORTING_TEST__.pending.length === count", arg=first + 1)
                page.locator("[data-workflow-stage-key='intent-contract-1'] button").click()
                self.settle_supporting_request(page, first, "reject")
                self.assertNotIn("obsolete handoff failure", page.locator("body").inner_text())
                self.assertNotIn("The workflow action did not complete", page.locator("body").inner_text())
                self.assertEqual(0, page.locator("[data-supporting-tool]").count())
                for outcome in ("resolve", "reject"):
                    first = page.evaluate("window.__SUPPORTING_TEST__.pending.length")
                    self.open_supporting_tool(page, "Model & Privacy Center")
                    page.wait_for_function(
                        "count => window.__SUPPORTING_TEST__.pending.length === count", arg=first + 1
                    )
                    self.assert_supporting_pending(page)
                    self.open_supporting_tool(page, "Local projects")
                    current = page.locator("[data-current-project]")
                    current.get_by_role("button", name="Close project", exact=True).click()
                    current.get_by_text("Closed", exact=True).wait_for(timeout=5000)
                    page.locator("[data-workflow-context]").wait_for(state="detached", timeout=5000)
                    self.assertEqual(0, page.locator("[data-workflow-context]").count())
                    self.assertNotIn("Preparing supporting-tool return", page.locator("body").inner_text())
                    current.get_by_role("button", name="Open project", exact=True).click()
                    page.locator("[data-workflow-nav]").wait_for(timeout=5000)
                    page.locator("[data-workflow-stage-key='intent-contract-1'] button").click()
                    self.settle_supporting_request(page, first, outcome)
                    self.assertNotIn("Preparing supporting-tool return", page.locator("body").inner_text())
                    self.assertNotIn("obsolete handoff failure", page.locator("body").inner_text())
                    self.assertNotIn("The workflow action did not complete", page.locator("body").inner_text())
                    self.assertEqual(0, page.locator("[data-supporting-tool]").count())
                first = page.evaluate("window.__SUPPORTING_TEST__.pending.length")
                self.open_supporting_tool(page, "Model & Privacy Center")
                page.wait_for_function("count => window.__SUPPORTING_TEST__.pending.length === count", arg=first + 1)
                self.assert_supporting_pending(page)
                self.settle_supporting_request(page, first, "reject")
                self.assertIn("The workflow action did not complete", page.locator("body").inner_text())
                self.assertIn("Supporting context expired", page.locator("[data-supporting-tool]").inner_text())
                self.assertNotIn("Preparing supporting-tool return", page.locator("body").inner_text())
                self.assertEqual(0, page.get_by_role("button", name="Return to current step", exact=False).count())
                self.assertEqual(
                    1,
                    page.evaluate("window.__SUPPORTING_TEST__.commands.filter(item => item.action === 'start').length"),
                )
                self.assertEqual([], errors)
            finally:
                context.close()
                browser.close()

    def test_populated_empty_failure_late_result_keyboard_and_responsive_states(self) -> None:
        self.assertEqual([], product_build_errors(REPO))
        document = inline_product_index(REPO)
        manifest = ModelManifest.model_validate(
            manifest_document()
            | {
                "identity": manifest_document()["identity"] | {"modelId": "fixture-" + "x" * 110},
            }
        )
        catalog = ModelRegistryCatalog(
            project_id="11111111-1111-4111-8111-111111111111", revision=1, manifests=(manifest,)
        )
        digest = canonical_hash(catalog)
        populated = {
            "schemaVersion": "1.0",
            "projectId": catalog.project_id,
            "revision": 1,
            "latestRevision": 1,
            "catalogHash": digest,
            "modelCount": 1,
            "inventoryState": "available",
            "executionAvailable": False,
            "entries": [
                {
                    "manifest": manifest.model_dump(mode="json", by_alias=True),
                    "manifestHash": canonical_hash(manifest),
                    "availability": "ready",
                    "qualifiedTaskKinds": ["generation"],
                    "reasonCodes": ["task-policy-check-required"],
                    "eligibility": "not-evaluated",
                }
            ],
            "nextManifestId": None,
            "nextHistoryRevision": None,
            "history": [
                {
                    "revision": 1,
                    "catalogHash": digest,
                    "recordHash": "sha256:" + "b" * 64,
                    "previousHash": None,
                    "occurredAt": "2026-09-06T12:00:00.000Z",
                    "modelCount": 1,
                }
            ],
        }
        fixture = (
            (REPO / "tests/desktop/fixtures/task_center_interactions.js")
            .read_text("utf-8")
            .replace(
                "__WORKFLOW_CATALOG__",
                core_workflow_catalog_json(REPO),
            )
        )
        wrapper = """(() => {
          const original = window.__TAURI_INTERNALS__.invoke;
          const populated = __CATALOG__;
          const state = window.__MODEL_TEST__ = { mode: 'populated', pending: null, reads: 0, mutations: 0 };
          const response = body => ({status: 200, contentType: 'application/json',
            traceId: 'a'.repeat(32), etag: null, body: JSON.stringify(body)});
          window.__TAURI_INTERNALS__.invoke = async (command, args) => {
            if (command !== 'core_api_request' || !args.request.path.startsWith('/projects/models')) {
              return original(command, args);
            }
            if (args.request.path.endsWith('/refresh')) state.mutations += 1;
            else state.reads += 1;
            if (state.mode === 'failure') throw Error('synthetic inventory failure');
            if (state.mode === 'pending') return await new Promise(resolve => {
              state.pending = () => resolve(response(populated));
            });
            if (state.mode === 'empty') return response({...populated,
              revision: 0, latestRevision: 0, catalogHash: null,
              modelCount: 0, entries: [], history: [], inventoryState: 'not-configured'});
            return response(populated);
          };
        })();""".replace("__CATALOG__", json.dumps(populated))
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 720}, reduced_motion="reduce")

            def route_application(route: Any) -> None:
                if route.request.url in {"http://tauri.localhost/", "http://tauri.localhost/index.html"}:
                    route.fulfill(status=200, content_type="text/html; charset=utf-8", body=document)
                else:
                    route.abort()

            context.route("**/*", route_application)
            page = context.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.add_init_script(fixture + DIRECTORY_PICKER_FIXTURE + wrapper)

            def open_tool(name: str) -> None:
                menu = page.locator("[data-all-tools]")
                if menu.get_attribute("open") is None:
                    menu.locator("summary").click()
                menu.get_by_role("button", name=name, exact=True).click()

            try:
                page.goto("http://tauri.localhost/index.html", wait_until="load")
                page.wait_for_function("document.body.dataset.applicationReady === 'true'", timeout=5000)
                open_tool("Model & Privacy Center")
                self.assertIn("Open a local project", page.locator("main").inner_text())
                self.assertEqual(0, page.evaluate("window.__MODEL_TEST__.reads"))
                open_tool("Local projects")
                choose_fixture_directory(page, "project-root", "C:/Research/study-one")
                page.get_by_role("button", name="Open project", exact=True).click()
                page.get_by_text("Exclusive local session open", exact=True).wait_for(timeout=5000)
                open_tool("Model & Privacy Center")
                page.get_by_role(
                    "heading", name=f"{manifest.identity.model_id} · {manifest.identity.model_version}", exact=True
                ).wait_for(timeout=5000)
                self.assertIn("Ready does not mean permission", page.locator("main").inner_text())
                for width, height in ((1440, 900), (1280, 720), (720, 450)):
                    page.set_viewport_size({"width": width, "height": height})
                    for _theme in ("light", "dark"):
                        self.assertFalse(page.evaluate("document.documentElement.scrollWidth > innerWidth + 1"))
                        page.locator("[data-theme-toggle]").click()
                        reload = page.get_by_role("button", name="Reload inventory", exact=True)
                        reload.focus()
                        page.keyboard.press("Tab")
                        self.assertEqual("Refresh recorded inventory", page.locator(":focus").inner_text())
                        page.keyboard.press("Shift+Tab")
                        self.assertEqual("Reload inventory", page.locator(":focus").inner_text())
                page.evaluate("window.__MODEL_TEST__.mode = 'failure'")
                page.get_by_role("button", name="Reload inventory", exact=True).click()
                page.get_by_text("Inventory unavailable", exact=True).wait_for(timeout=5000)
                self.assertNotIn(manifest.identity.model_id, page.locator("main").inner_text())
                self.assertNotIn("No models are recorded", page.locator("main").inner_text())
                page.evaluate("window.__MODEL_TEST__.mode = 'empty'")
                page.get_by_role("button", name="Reload inventory", exact=True).click()
                page.get_by_text("No models are recorded", exact=True).wait_for(timeout=5000)
                self.assertTrue(page.get_by_role("button", name="Refresh recorded inventory", exact=True).is_disabled())
                page.evaluate("window.__MODEL_TEST__.mode = 'pending'")
                page.get_by_role("button", name="Reload inventory", exact=True).click()
                page.wait_for_function("window.__MODEL_TEST__.pending !== null")
                open_tool("Local projects")
                page.evaluate("window.__MODEL_TEST__.pending()")
                self.assertNotIn(manifest.identity.model_id, page.locator("main").inner_text())
                self.assertEqual(0, page.evaluate("window.__MODEL_TEST__.mutations"))
                self.assertEqual([], errors)
            finally:
                context.close()
                browser.close()


if __name__ == "__main__":
    unittest.main()
