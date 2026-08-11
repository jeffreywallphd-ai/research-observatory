from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from desktop_app_check import (  # noqa: E402
    command_plan,
    component_catalog_browser_errors,
    design_system_errors,
    product_build_errors,
    runtime_frame_errors,
    security_errors,
    tool_environment,
)


class DesktopAppCheckTests(unittest.TestCase):
    def test_built_product_is_functional_cap01_only_and_keyboard_accessible(self) -> None:
        errors, details = runtime_frame_errors(REPO)

        self.assertEqual([], errors)
        self.assertEqual(1, details["pages"])
        self.assertEqual(["CAP-01"], details["implementedCapabilities"])
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
        self.assertTrue(details["retainedInput"])
        self.assertTrue(details["diagnosticCopy"])
        self.assertEqual(2, details["responsiveCases"])
        self.assertEqual([], details["criticalViolations"])
        self.assertEqual([], details["requests"])
        self.assertEqual(6, details["designSystem"]["cases"])

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
        self.assertTrue(any("zero privileged" in error for error in errors))

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


if __name__ == "__main__":
    unittest.main()
