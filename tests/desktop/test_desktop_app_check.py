from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from desktop_app_check import (  # noqa: E402
    command_plan,
    design_system_errors,
    runtime_frame_errors,
    security_errors,
    tool_environment,
)


class DesktopAppCheckTests(unittest.TestCase):
    def test_built_runtime_activates_every_frame_and_keyboard_boundary(self) -> None:
        errors, details = runtime_frame_errors(REPO)

        self.assertEqual([], errors)
        self.assertEqual(32, details["pages"])
        self.assertEqual(6, details["routeRecoveryCases"])
        self.assertEqual(2, details["hrefRecoveryCases"])
        self.assertGreater(details["workspaceNavigationItems"], 1)
        self.assertTrue(details["keyboardRail"])
        self.assertTrue(details["commandFocus"])
        self.assertEqual([], details["requests"])
        self.assertEqual(6, details["designSystem"]["cases"])
        project = details["projectSelection"]
        self.assertEqual(4, project["recentProjects"])
        self.assertEqual(1, project["missingProjects"])
        self.assertTrue(project["persistentRemoval"])
        self.assertTrue(project["emptyState"])
        self.assertTrue(project["preferenceRecovery"])
        self.assertTrue(project["writeFailurePreserved"])
        self.assertEqual(
            ["locate-existing", "open-existing", "remove-recent", "create-new"],
            [intent["type"] for intent in project["intents"]],
        )

    def test_security_boundary_and_complete_command_plan(self) -> None:
        self.assertEqual([], security_errors(REPO))
        commands = command_plan(REPO)
        self.assertEqual(8, len(commands))
        rendered = [" ".join(command) for command in commands]
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

    def test_design_system_is_reference_bound_and_rejects_literal_color_drift(self) -> None:
        self.assertEqual([], design_system_errors(REPO))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "repo"
            shutil.copytree(REPO / "packages" / "ui-tokens", root / "packages" / "ui-tokens")
            shutil.copytree(REPO / "packages" / "ui-components", root / "packages" / "ui-components")
            token_source = root / "design" / "ui-reference" / "assets" / "tokens.css"
            token_source.parent.mkdir(parents=True)
            shutil.copy2(REPO / "design" / "ui-reference" / "assets" / "tokens.css", token_source)
            styles = root / "packages" / "ui-components" / "src" / "styles.css"
            styles.write_text(styles.read_text(encoding="utf-8") + "\n.attack { color: #ffffff; }\n", encoding="utf-8")
            transport = root / "packages" / "ui-tokens" / "index.css"
            transport.write_text('@import "https://example.invalid/tokens.css";\n', encoding="utf-8")

            errors = design_system_errors(root)

        self.assertTrue(any("literal colors" in error for error in errors), errors)
        self.assertTrue(any("governed reference source" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
