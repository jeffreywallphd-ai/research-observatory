from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from desktop_app_check import (  # noqa: E402
    command_plan,
    component_catalog_browser_errors,
    core_workflow_catalog_json,
    design_system_errors,
    inline_product_index,
    page_error_collector,
    product_build_errors,
    runtime_frame_errors,
    security_errors,
    tool_environment,
)


class DesktopAppCheckTests(unittest.TestCase):
    def test_built_product_exposes_only_implemented_functional_workspaces_and_is_keyboard_accessible(self) -> None:
        errors, details = runtime_frame_errors(REPO)

        self.assertEqual([], errors)
        self.assertEqual(1, details["pages"])
        self.assertEqual(
            [
                "CAP-01",
                "CAP-02.S01.T03",
                "CAP-02.S04.T02",
                "CAP-02.S04.T03",
                "CAP-03.S02.T02",
                "CAP-03.S03.T03",
                "CAP-03.S05.T03",
                "CAP-03.S06.T02",
                "CAP-03.S06.T03",
                "CAP-03.S06.T04",
                "CAP-03.S06.T05",
            ],
            details["implementedCapabilities"],
        )
        self.assertTrue(details["adaptiveWorkflowNavigation"])
        self.assertTrue(details["workflowProfileMatrixValid"])
        matrix = details["workflowProfileMatrix"]
        self.assertEqual("RO-UI-ACADEMIC-MINIMAL-1.5", matrix["referenceId"])
        self.assertEqual("1.5", matrix["referenceVersion"])
        self.assertEqual("1.0.0", matrix["profileCatalogVersion"])
        self.assertEqual(
            "sha256:0a3887774b30bb2d2d7fced5c9e43452e7e34993407a6122155b740814350e49",
            matrix["profileCatalogHash"],
        )
        self.assertEqual(
            "sha256:2feffbaf216da3adb4d8fe0b3ca6e2579cdc2dcedc2d57341086a14def5fe0d2",
            matrix["intentGuidanceHash"],
        )
        self.assertTrue(matrix["allToolsAccessible"])
        self.assertEqual(14, len(matrix["profiles"]))
        self.assertEqual(
            {"hermeneutic-inquiry", "living-review", "manuscript-review-revision"},
            {profile["profileId"] for profile in matrix["profiles"] if profile["processForm"] == "revisitable"},
        )
        self.assertTrue(all(profile["valid"] for profile in matrix["profiles"]))
        self.assertTrue(details["intentMutationRaceGuarded"])
        self.assertEqual(0, details["referenceOnlyPages"])
        self.assertTrue(details["commandFocus"])
        self.assertTrue(details["skipLink"])
        self.assertTrue(details["shortcutDialog"])
        self.assertTrue(details["focusContainment"])
        self.assertTrue(details["focusRestoration"])
        self.assertTrue(details["focusVisible"])
        self.assertTrue(details["keyboardCommand"])
        self.assertTrue(details["homeShortcut"])
        self.assertTrue(details["themeToggle"])
        self.assertTrue(details["liveRegion"])
        self.assertTrue(details["boundaryState"])
        self.assertTrue(details["boundaryRecovery"])
        self.assertTrue(details["applicationLockEventAclStartup"])
        self.assertEqual(
            {
                "defaultNoLogin": True,
                "deniedListener": True,
                "timedOutListener": True,
                "malformedEvent": True,
            },
            details["applicationLockEventAclStartupCases"],
        )
        self.assertTrue(details["retainedInput"])
        self.assertTrue(details["diagnosticCopy"])
        self.assertEqual(2, details["responsiveCases"])
        self.assertEqual([], details["criticalViolations"])
        self.assertEqual([], details["requests"])
        self.assertEqual(6, details["designSystem"]["cases"])
        self.assertEqual(10_000, details["largeTable"]["totalRows"])
        self.assertEqual(50, details["largeTable"]["maximumRenderedRows"])
        self.assertTrue(details["largeTable"]["keyboardTransitions"])
        self.assertTrue(details["largeTable"]["focusPreserved"])
        self.assertTrue(details["largeTable"]["disabledBoundaries"])
        self.assertTrue(details["largeTable"]["compact"])

    def test_security_boundary_and_complete_command_plan(self) -> None:
        self.assertEqual([], security_errors(REPO))
        commands = command_plan(REPO)
        self.assertEqual(9, len(commands))
        rendered = [" ".join(command) for command in commands]
        self.assertTrue(any("ui-components" in command and "verify" in command for command in rendered))
        self.assertTrue(any("pnpm" in command and "build" in command for command in rendered))
        self.assertTrue(any("clippy" in command and "--locked" in command for command in rendered))
        self.assertTrue(any("cargo.exe test" in command and "--locked" in command for command in rendered))
        self.assertEqual("true", tool_environment(REPO)[0]["CI"])

    def test_external_development_url_and_privilege_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            source = REPO / "apps" / "desktop" / "src-tauri"
            shutil.copytree(source, root / "apps" / "desktop" / "src-tauri")
            config_path = root / "apps" / "desktop" / "src-tauri" / "tauri.conf.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["build"]["devUrl"] = "https://example.invalid"
            config["app"]["security"]["csp"] += "; connect-src https://example.invalid"
            config_path.write_text(json.dumps(config), encoding="utf-8", newline="\n")
            capability_path = root / "apps" / "desktop" / "src-tauri" / "capabilities" / "main-window.json"
            capability = json.loads(capability_path.read_text(encoding="utf-8"))
            capability["permissions"] = ["core:default"]
            capability_path.write_text(json.dumps(capability), encoding="utf-8", newline="\n")

            errors = security_errors(root)

        self.assertTrue(any("development URL" in error for error in errors))
        self.assertTrue(any("Tauri CSP" in error for error in errors))
        self.assertTrue(any("receive-only event permissions" in error for error in errors))

    def test_event_capability_rejects_missing_widened_or_renderer_write_authority(self) -> None:
        devtools = "core:webview:allow-internal-toggle-devtools"
        listen = "core:event:allow-listen"
        unlisten = "core:event:allow-unlisten"
        expected = [devtools, listen, unlisten]
        adversarial_capabilities = {
            "missing-listen": {"permissions": [devtools, unlisten]},
            "missing-unlisten": {"permissions": [devtools, listen]},
            "added-emit": {"permissions": [*expected, "core:event:allow-emit"]},
            "added-emit-to": {"permissions": [*expected, "core:event:allow-emit-to"]},
            "added-event-default": {"permissions": [*expected, "core:event:default"]},
            "added-core-default": {"permissions": [*expected, "core:default"]},
            "added-arbitrary-permission": {"permissions": [*expected, "core:app:allow-version"]},
            "widened-windows": {"permissions": expected, "windows": ["main", "*"]},
            "remote-origin": {
                "permissions": expected,
                "remote": {"urls": ["https://example.invalid"]},
            },
        }

        for case, mutation in adversarial_capabilities.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "repo"
                source = REPO / "apps" / "desktop" / "src-tauri"
                shutil.copytree(source, root / "apps" / "desktop" / "src-tauri")
                capability_path = root / "apps" / "desktop" / "src-tauri" / "capabilities" / "main-window.json"
                capability = json.loads(capability_path.read_text(encoding="utf-8"))
                capability.update(mutation)
                capability_path.write_text(json.dumps(capability), encoding="utf-8", newline="\n")

                errors = security_errors(root)

                self.assertTrue(
                    any("receive-only event permissions" in error for error in errors),
                    errors,
                )

    def test_generated_capability_projection_cannot_diverge(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            source = REPO / "apps" / "desktop" / "src-tauri"
            shutil.copytree(source, root / "apps" / "desktop" / "src-tauri")
            generated_path = root / "apps" / "desktop" / "src-tauri" / "gen" / "schemas" / "capabilities.json"
            generated = json.loads(generated_path.read_text(encoding="utf-8"))
            generated["main-window"]["permissions"].append("core:event:allow-emit")
            generated_path.write_text(json.dumps(generated), encoding="utf-8", newline="\n")

            errors = security_errors(root)

        self.assertTrue(any("generated Tauri capability projection" in error for error in errors), errors)

    def test_product_bundle_rejects_reference_pages_and_tauri_fixture_redirect(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            shutil.copytree(
                REPO / "apps" / "desktop",
                root / "apps" / "desktop",
                ignore=shutil.ignore_patterns("dist", "node_modules", "target"),
            )
            for package in ("ui-components", "ui-tokens"):
                shutil.copytree(
                    REPO / "packages" / package,
                    root / "packages" / package,
                    ignore=shutil.ignore_patterns("node_modules", "target"),
                )
            for relative in ("Cargo.toml", "Cargo.lock", "package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml"):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(REPO / relative, destination)
            activation = root / "verification" / "extensions" / "desktop-ui.json"
            activation.parent.mkdir(parents=True)
            shutil.copy2(REPO / "verification" / "extensions" / "desktop-ui.json", activation)
            site = root / "design" / "ui-reference" / "SITE_MANIFEST.json"
            site.parent.mkdir(parents=True)
            shutil.copy2(REPO / "design" / "ui-reference" / "SITE_MANIFEST.json", site)
            component_source = root / "packages" / "ui-components" / "src" / "index.tsx"
            component_source.write_text(
                component_source.read_text(encoding="utf-8") + "\n// unbound product source\n",
                encoding="utf-8",
                newline="\n",
            )
            source_errors = product_build_errors(root)
            self.assertTrue(any("exact product build inputs" in error for error in source_errors), source_errors)
            shutil.copy2(REPO / "packages" / "ui-components" / "src" / "index.tsx", component_source)
            (root / "apps" / "desktop" / "product-dist" / "study-design.html").write_text(
                "<!doctype html><title>reference leak</title>", encoding="utf-8"
            )
            config_path = root / "apps" / "desktop" / "src-tauri" / "tauri.conf.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["build"]["frontendDist"] = "../dist"
            config_path.write_text(json.dumps(config), encoding="utf-8", newline="\n")

            errors = product_build_errors(root)

        self.assertTrue(any("only the functional index/runtime inventory" in error for error in errors), errors)
        self.assertTrue(any("serve only apps/desktop/product-dist" in error for error in errors), errors)
        self.assertTrue(any("reference-only pages" in error for error in errors), errors)

    def test_every_unreviewed_connection_source_fails_closed(self) -> None:
        for source in (
            "wss://example.invalid",
            "data:",
            "example.invalid",
            "ipc.evil:",
            "http://ipc.localhost.evil",
        ):
            with self.subTest(source=source), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "repo"
                tauri = REPO / "apps" / "desktop" / "src-tauri"
                shutil.copytree(tauri, root / "apps" / "desktop" / "src-tauri")
                config_path = root / "apps" / "desktop" / "src-tauri" / "tauri.conf.json"
                config = json.loads(config_path.read_text(encoding="utf-8"))
                config["app"]["security"]["csp"] = config["app"]["security"]["csp"].replace(
                    "connect-src ipc: http://ipc.localhost",
                    f"connect-src ipc: http://ipc.localhost {source}",
                )
                config_path.write_text(json.dumps(config), encoding="utf-8", newline="\n")

                errors = security_errors(root)

            self.assertTrue(any("offline source allowlist" in error for error in errors), errors)

    def test_design_system_is_reference_bound_and_rejects_all_literal_style_drift(self) -> None:
        self.assertEqual([], design_system_errors(REPO))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            shutil.copytree(REPO / "packages" / "ui-tokens", root / "packages" / "ui-tokens")
            shutil.copytree(REPO / "packages" / "ui-components", root / "packages" / "ui-components")
            token_source = root / "design" / "ui-reference" / "assets" / "tokens.css"
            token_source.parent.mkdir(parents=True)
            shutil.copy2(REPO / "design" / "ui-reference" / "assets" / "tokens.css", token_source)
            shutil.copy2(REPO / "pnpm-lock.yaml", root / "pnpm-lock.yaml")
            styles = root / "packages" / "ui-components" / "src" / "styles.css"
            styles.write_text(styles.read_text(encoding="utf-8") + "\n.attack { color: red; }\n", encoding="utf-8")
            components = root / "packages" / "ui-components" / "src" / "index.tsx"
            components.write_text(
                components.read_text(encoding="utf-8")
                + "\nexport function Attack() { return <span style={{ color: 'red' }}>attack</span>; }\n",
                encoding="utf-8",
            )
            transport = root / "packages" / "ui-tokens" / "index.css"
            transport.write_text('@import "https://example.invalid/tokens.css";\n', encoding="utf-8")
            catalog = root / "packages" / "ui-components" / "catalog.html"
            catalog.write_text(
                catalog.read_text(encoding="utf-8").replace(
                    'data-boundary-state="recovery-required"', 'data-boundary-state="failed"', 1
                ),
                encoding="utf-8",
                newline="\n",
            )

            errors = design_system_errors(root)

        self.assertTrue(any("governed tokens" in error for error in errors), errors)
        self.assertTrue(any("inline styles" in error for error in errors), errors)
        self.assertTrue(any("governed reference source" in error for error in errors), errors)
        self.assertTrue(any("every governed boundary state" in error for error in errors), errors)

    def test_catalog_structure_and_accessible_name_cannot_be_satisfied_by_comments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            shutil.copytree(REPO / "packages" / "ui-tokens", root / "packages" / "ui-tokens")
            shutil.copytree(REPO / "packages" / "ui-components", root / "packages" / "ui-components")
            token_source = root / "design" / "ui-reference" / "assets" / "tokens.css"
            token_source.parent.mkdir(parents=True)
            shutil.copy2(REPO / "design" / "ui-reference" / "assets" / "tokens.css", token_source)
            shutil.copy2(REPO / "pnpm-lock.yaml", root / "pnpm-lock.yaml")
            catalog_path = root / "packages" / "ui-components" / "catalog.html"
            catalog = catalog_path.read_text(encoding="utf-8")
            catalog = re.sub(r'<article class="ro-panel".*?</article>', "", catalog)
            catalog = catalog.replace('id="catalog-dialog-title"', "")
            catalog = catalog.replace("</main>", "<!-- ro-panel --></main>")
            catalog_path.write_text(catalog, encoding="utf-8")

            static_errors = design_system_errors(root)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context()
                browser_errors, _ = component_catalog_browser_errors(root, context)
                context.close()
                browser.close()

        self.assertTrue(any("no structural ro-panel" in error for error in static_errors), static_errors)
        self.assertTrue(any("dangling or empty" in error for error in static_errors), static_errors)
        self.assertTrue(any("structural inventory" in error for error in browser_errors), browser_errors)
        self.assertTrue(any("semantics are incomplete" in error for error in browser_errors), browser_errors)


class TaskCenterInteractionTests(unittest.TestCase):
    def test_commands_focus_failure_and_project_switch_are_bound_to_current_projection(self) -> None:
        self.assertEqual([], product_build_errors(REPO))
        document = inline_product_index(REPO)
        fixture = (
            (REPO / "tests" / "desktop" / "fixtures" / "task_center_interactions.js")
            .read_text(encoding="utf-8")
            .replace("__WORKFLOW_CATALOG__", core_workflow_catalog_json(REPO))
        )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context()

            def serve_application(route: Any) -> None:
                if route.request.url in {"http://tauri.localhost/", "http://tauri.localhost/index.html"}:
                    route.fulfill(status=200, content_type="text/html; charset=utf-8", body=document)
                else:
                    route.abort()

            context.route("**/*", serve_application)
            page = context.new_page()
            page_errors: list[str] = []
            page.on("pageerror", page_error_collector(page_errors))
            page.add_init_script(fixture)

            def open_desktop_tool(name: str) -> None:
                disclosure = page.locator("[data-all-tools]")
                if disclosure.get_attribute("open") is None:
                    disclosure.locator("summary").click()
                disclosure.get_by_role("button", name=name, exact=True).click()

            try:
                page.goto("http://tauri.localhost/index.html", wait_until="load")
                page.wait_for_function("document.body.dataset.applicationReady === 'true'", timeout=5_000)
                open_desktop_tool("Local projects")
                page.locator("#project-parent-directory").fill("C:/Research")
                page.locator("#project-directory-name").fill("study-one")
                page.locator("#project-display-name").fill("Study One")
                page.locator("#project-research-objective").fill("Explain a bounded workflow.")
                page.locator("#project-primary-use-case").select_option("theory-synthesis")
                page.get_by_role("button", name="Create project", exact=True).click()
                page.get_by_label("Current project actions").get_by_role(
                    "button", name="Open project", exact=True
                ).click()
                page.get_by_text("Exclusive local session open", exact=True).wait_for(timeout=5_000)
                open_desktop_tool("Task Center")
                page.get_by_role("heading", name="project-a-extract", exact=True).wait_for(timeout=5_000)

                cancel = page.get_by_role("button", name="Cancel safely", exact=True)
                cancel.click()
                dialog = page.get_by_role("alertdialog")
                dialog.wait_for(state="visible", timeout=5_000)
                self.assertEqual("Keep current state", page.locator(":focus").inner_text())
                page.keyboard.press("Shift+Tab")
                self.assertEqual("Confirm", page.locator(":focus").inner_text())
                page.keyboard.press("Tab")
                self.assertEqual("Keep current state", page.locator(":focus").inner_text())
                page.keyboard.press("Escape")
                dialog.wait_for(state="detached", timeout=5_000)
                page.wait_for_function("document.activeElement?.textContent?.trim() === 'Cancel safely'", timeout=5_000)

                page.evaluate("window.__FAIL_NEXT_CANCEL__()")
                cancel.click()
                page.get_by_role("button", name="Confirm", exact=True).click()
                page.get_by_text("Task Center unavailable", exact=True).wait_for(timeout=5_000)
                page.wait_for_function(
                    "document.querySelector('[data-live-region]')?.textContent?.includes('Task Center command failed')",
                    timeout=5_000,
                )
                self.assertEqual(1, dialog.count())
                page.get_by_role("button", name="Keep current state", exact=True).click()
                page.wait_for_function("document.activeElement?.textContent?.trim() === 'Cancel safely'", timeout=5_000)

                cancel.click()
                page.get_by_role("button", name="Confirm", exact=True).click()
                dialog.wait_for(state="detached", timeout=5_000)
                page.get_by_text("cancelling", exact=True).wait_for(timeout=5_000)
                page.wait_for_function(
                    "document.activeElement?.getAttribute('aria-pressed') === 'true'",
                    timeout=5_000,
                )

                page.evaluate("window.__DELAY_NEXT_A__()")
                page.get_by_role("button", name="Refresh", exact=True).click()
                open_desktop_tool("Local projects")
                page.locator("#project-root").fill("C:/Research/study-two")
                page.locator("form").filter(has=page.locator("#project-root")).get_by_role(
                    "button", name="Open project", exact=True
                ).click()
                page.get_by_text("Study Two", exact=True).wait_for(timeout=5_000)
                open_desktop_tool("Task Center")
                page.get_by_role("heading", name="project-b-review", exact=True).wait_for(timeout=5_000)
                page.evaluate("window.__RESOLVE_A__()")
                page.wait_for_timeout(100)
                self.assertEqual(0, page.get_by_text("project-a-extract", exact=True).count())
                self.assertIn("Continuation of run", page.locator("[data-workflow-continuation]").inner_text())

                page.get_by_role("button", name="approved — resume workflow", exact=True).click()
                page.get_by_text("succeeded", exact=True).wait_for(timeout=5_000)
                self.assertEqual(0, page.get_by_role("heading", name="Decision required", exact=True).count())
                self.assertEqual([], page_errors)
            finally:
                page.close()
                context.close()
                browser.close()


if __name__ == "__main__":
    unittest.main()
