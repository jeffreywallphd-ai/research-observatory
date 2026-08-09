#!/usr/bin/env python3
"""Build and validate the pinned offline Tauri/React desktop application."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright
from ui_conformance import inline_page, load_context

Runner = Callable[..., subprocess.CompletedProcess[str]]
EXPECTED_CSP = {
    "default-src": ("'self'",),
    "img-src": ("'self'", "data:"),
    "style-src": ("'self'", "'unsafe-inline'"),
    "script-src": ("'self'",),
    "connect-src": ("ipc:", "http://ipc.localhost"),
    "font-src": ("'self'",),
    "object-src": ("'none'",),
    "base-uri": ("'none'",),
    "frame-ancestors": ("'none'",),
    "form-action": ("'self'",),
}
ROUTE_RECOVERY_CASES = (
    "%252e%252e/study-design.html",
    "%5c/study-design.html",
    "%2f%2fevil.invalid/study-design.html",
    "%68ttps%3A%2F%2Fevil.invalid/study-design.html",
    "https:evil.invalid/study-design.html",
    "mailto:user@example.invalid/study-design.html",
)
HREF_RECOVERY_CASES = (
    "https:evil.invalid/study-design.html",
    "mailto:user@example.invalid/study-design.html",
)


def csp_directives(raw: str) -> tuple[dict[str, tuple[str, ...]], list[str]]:
    directives: dict[str, tuple[str, ...]] = {}
    errors: list[str] = []
    for raw_part in raw.split(";"):
        part = raw_part.strip()
        if not part:
            continue
        tokens = part.split()
        name = tokens[0]
        if name in directives:
            errors.append(f"Tauri CSP repeats directive {name}")
            continue
        directives[name] = tuple(tokens[1:])
    return directives, errors


def json_object(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return loaded


def security_errors(repo: Path) -> list[str]:
    errors: list[str] = []
    config = json_object(repo / "apps" / "desktop" / "src-tauri" / "tauri.conf.json")
    build = config.get("build")
    app = config.get("app")
    if not isinstance(build, dict) or build.get("frontendDist") != "../dist" or "devUrl" in build:
        errors.append("Tauri must load the packaged desktop build without a development URL")
    if not isinstance(app, dict):
        errors.append("Tauri application configuration is missing")
        return errors
    security = app.get("security")
    if not isinstance(security, dict):
        errors.append("Tauri security configuration is missing")
        return errors
    csp = security.get("csp")
    if isinstance(csp, str):
        observed_csp, csp_errors = csp_directives(csp)
        errors.extend(csp_errors)
        if observed_csp != EXPECTED_CSP:
            errors.append("Tauri CSP must exactly match the reviewed offline source allowlist")
    else:
        errors.append("Tauri CSP must be an explicit string source allowlist")
    if security.get("capabilities") != ["main-window"] or app.get("withGlobalTauri") is not False:
        errors.append("Tauri must expose only the named main-window capability without a global bridge")
    capability = json_object(repo / "apps" / "desktop" / "src-tauri" / "capabilities" / "main-window.json")
    if capability.get("windows") != ["main"] or capability.get("permissions") != []:
        errors.append("the initial desktop capability must grant zero privileged commands to the main window")
    return errors


def tool_environment(repo: Path) -> tuple[dict[str, str], Path, Path]:
    node_root = repo / ".local" / "toolchains" / "node-v24.19.0-win-x64"
    corepack = node_root / "corepack.cmd"
    cargo_root = repo / ".local" / "toolchains" / "cargo"
    cargo = cargo_root / "bin" / "cargo.exe"
    for path in (node_root / "node.exe", corepack, cargo):
        if not path.is_file():
            raise ValueError(f"pinned desktop tool is unavailable: {path.relative_to(repo).as_posix()}")
    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join((str(node_root), str(cargo.parent), environment.get("PATH", "")))
    environment["COREPACK_HOME"] = str(repo / ".local" / "toolchains" / "corepack")
    environment["CARGO_HOME"] = str(cargo_root)
    environment["RUSTUP_HOME"] = str(repo / ".local" / "toolchains" / "rustup")
    return environment, corepack, cargo


def command_plan(repo: Path) -> list[list[str]]:
    _, corepack, cargo = tool_environment(repo)
    app = str(repo / "apps" / "desktop")
    return [
        [str(corepack), "pnpm", "--dir", app, "lint"],
        [str(corepack), "pnpm", "--dir", app, "typecheck"],
        [str(corepack), "pnpm", "--dir", app, "test"],
        [str(corepack), "pnpm", "--dir", app, "build"],
        [str(cargo), "fmt", "--all", "--check"],
        [str(cargo), "clippy", "--workspace", "--all-targets", "--locked", "--", "-D", "warnings"],
        [str(cargo), "test", "--workspace", "--locked"],
        [str(cargo), "build", "--workspace", "--locked"],
    ]


def page_error_collector(target: list[str]) -> Callable[[PlaywrightError], None]:
    def collect(error: PlaywrightError) -> None:
        target.append(str(error))

    return collect


def runtime_frame_errors(repo: Path) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    context = load_context(repo)
    runtime = (context.target / "runtime" / "main.js").read_text(encoding="utf-8")
    if "process.env.NODE_ENV" in runtime:
        errors.append("desktop production runtime retains an unresolved Node environment expression")
    details: dict[str, Any] = {
        "pages": 0,
        "routeRecoveryCases": 0,
        "hrefRecoveryCases": 0,
        "workspaceNavigationItems": None,
        "keyboardRail": False,
        "commandFocus": False,
        "requests": [],
    }
    documents: dict[str, str] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        browser_context = browser.new_context()

        def serve_application(route: Any) -> None:
            document = documents.get(route.request.url)
            if document is None:
                details["requests"].append(route.request.url)
                route.abort()
            else:
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=document)

        browser_context.route("**/*", serve_application)
        try:
            for page_name in context.pages:
                page = browser_context.new_page()
                page_errors: list[str] = []
                page.on("pageerror", page_error_collector(page_errors))
                html = inline_page(context, page_name).replace(
                    "</body>", f'<script type="module">{runtime}</script></body>'
                )
                page_url = f"http://tauri.localhost/{page_name}"
                documents[page_url] = html
                page.goto(page_url, wait_until="load")
                page.wait_for_function("document.body.dataset.applicationFrame === 'ready'", timeout=5_000)
                current_workspace = page.locator("body").get_attribute("data-current-workspace")
                if current_workspace != page_name:
                    errors.append(f"{page_name}: application frame marked current workspace {current_workspace!r}")
                if page_name == "study-design.html":
                    navigation_count = page.locator("body").get_attribute("data-navigation-workspaces")
                    details["workspaceNavigationItems"] = int(navigation_count or "0")
                if page_errors:
                    errors.append(f"{page_name}: runtime error: {'; '.join(page_errors)}")
                details["pages"] += 1
                if page_name == "index.html":
                    first = page.locator("aside.sidebar a.nav-item[href]").first
                    first.focus()
                    before = page.evaluate("document.activeElement?.getAttribute('href')")
                    page.keyboard.press("ArrowDown")
                    after = page.evaluate("document.activeElement?.getAttribute('href')")
                    details["keyboardRail"] = isinstance(after, str) and after != before
                    page.keyboard.press("Control+K")
                    details["commandFocus"] = page.evaluate(
                        "document.activeElement?.matches(\"label.global-search input[type='search']\") === true"
                    )
                page.close()
            recovery_html = inline_page(context, "index.html").replace(
                "</body>", f'<script type="module">{runtime}</script></body>'
            )
            for route_case in ROUTE_RECOVERY_CASES:
                page = browser_context.new_page()
                page_url = f"http://tauri.localhost/{route_case}"
                documents[page_url] = recovery_html
                page.goto(page_url, wait_until="load")
                page.wait_for_function("document.body.dataset.applicationFrame === 'ready'", timeout=5_000)
                current_workspace = page.locator("body").get_attribute("data-current-workspace")
                if current_workspace != "index.html":
                    errors.append(f"{route_case}: unsafe route recovered to {current_workspace!r}")
                details["routeRecoveryCases"] += 1
                page.close()
            for href_case in HREF_RECOVERY_CASES:
                page = browser_context.new_page()
                page_errors = []
                page.on("pageerror", page_error_collector(page_errors))
                href_html = (
                    inline_page(context, "study-design.html")
                    .replace('href="study-design.html"', f'href="{href_case}"', 1)
                    .replace("</body>", f'<script type="module">{runtime}</script></body>')
                )
                page_url = "http://tauri.localhost/study-design.html"
                documents[page_url] = href_html
                page.goto(page_url, wait_until="load")
                page.wait_for_function("document.body.dataset.applicationFrame === 'ready'", timeout=5_000)
                unsafe_anchor = page.locator(f'aside.sidebar a.nav-item[href="{href_case}"]').first
                if unsafe_anchor.get_attribute("aria-current") == "page":
                    errors.append(f"{href_case}: external-looking href was marked as the current local workspace")
                unsafe_anchor.focus()
                before_focus = page.evaluate("document.activeElement?.getAttribute('href')")
                page.keyboard.press("ArrowDown")
                after_focus = page.evaluate("document.activeElement?.getAttribute('href')")
                if after_focus != before_focus:
                    errors.append(f"{href_case}: external-looking href remained in keyboard navigation")
                if page_errors:
                    errors.append(f"{href_case}: runtime error: {'; '.join(page_errors)}")
                details["hrefRecoveryCases"] += 1
                page.close()
        except (OSError, PlaywrightError, ValueError) as exc:
            errors.append(f"desktop built-runtime browser check failed: {exc}")
        finally:
            browser_context.close()
            browser.close()
    if details["requests"]:
        errors.append("desktop built runtime attempted external resource requests")
    if not details["keyboardRail"]:
        errors.append("desktop navigation rail did not move keyboard focus to a distinct workspace")
    if not details["commandFocus"]:
        errors.append("desktop Ctrl+K command shortcut did not focus project search")
    return errors, details


def validate(repo: Path, runner: Runner = subprocess.run) -> dict[str, Any]:
    errors = security_errors(repo)
    commands: list[dict[str, Any]] = []
    frame: dict[str, Any] = {}
    if errors:
        return {"ok": False, "commands": commands, "errors": errors}
    environment, _, _ = tool_environment(repo)
    for argv in command_plan(repo):
        completed = runner(argv, cwd=repo, env=environment, capture_output=True, text=True, check=False)
        commands.append({"argv": argv, "exitCode": completed.returncode})
        if completed.returncode:
            diagnostic = (completed.stderr or completed.stdout).strip()
            errors.append(f"desktop command failed ({subprocess.list2cmdline(argv)}): {diagnostic}")
            break
    if not errors:
        try:
            context = load_context(repo)
            if context.config["mode"] != "approved-reference-application":
                errors.append("desktop verification did not target the built application")
            frame_errors, frame = runtime_frame_errors(repo)
            errors.extend(frame_errors)
        except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(str(exc))
    return {"ok": not errors, "commands": commands, "errors": errors, "frame": frame}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve(strict=True)
    try:
        report = validate(repo)
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        report = {"ok": False, "commands": [], "errors": [str(exc)]}
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        output = (repo / args.report).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8", newline="\n")
    print(payload, end="")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
