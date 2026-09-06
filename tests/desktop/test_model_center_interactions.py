from __future__ import annotations

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
