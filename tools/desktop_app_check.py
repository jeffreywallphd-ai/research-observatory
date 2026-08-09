#!/usr/bin/env python3
"""Build and validate the pinned offline Tauri/React desktop application."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import yaml
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
TOKEN_CONTRACT_KEYS = {
    "schemaVersion",
    "documentType",
    "contractVersion",
    "referenceId",
    "referenceVersion",
    "referencePackageSha256",
    "sourcePath",
    "sourceCanonicalSha256",
    "transport",
    "themes",
}
EXPECTED_TOKEN_CONTRACT = {
    "schemaVersion": "1.0",
    "documentType": "design-token-contract",
    "contractVersion": "1.0.0",
    "referenceId": "RO-UI-ACADEMIC-MINIMAL-1.3",
    "referenceVersion": "1.3",
    "referencePackageSha256": "db13c8d5eeee71c890ca8530d7355a7fa95ca17630e8d53adba4fc7724d609e2",
    "sourcePath": "design/ui-reference/assets/tokens.css",
    "sourceCanonicalSha256": "e6aa1ebf847e983f4f5c9d20ad0e753716737cdfbedf617df2292bf510bebfa5",
    "transport": "css-custom-properties",
    "themes": ["light", "dark"],
}
EXPECTED_TOKEN_TRANSPORT = '@import "../../design/ui-reference/assets/tokens.css";\n'
REQUIRED_COMPONENT_MARKERS = (
    "ro-typography",
    "ro-icon",
    "ro-button",
    "ro-field",
    "ro-table",
    "ro-dialog",
    "ro-notification",
    "ro-status-badge",
    "ro-panel",
    "ro-evidence-state",
    "ro-uncertainty-state",
)
REQUIRED_COMPONENT_EXPORTS = (
    "Typography",
    "Icon",
    "Button",
    "Field",
    "DataTable",
    "DialogSurface",
    "Notification",
    "StatusBadge",
    "Panel",
    "EvidenceStateBadge",
    "UncertaintyState",
)
EXPECTED_EVIDENCE_STATES = {
    "observed",
    "extracted",
    "inferred",
    "verified",
    "disputed",
    "adjudicated",
    "stale",
}
EXPECTED_UNCERTAINTY_STATES = {"unknown", "not-reported", "not-applicable", "ambiguous"}
CONTRAST_PAIRS = (
    ("text-strong", "surface-1"),
    ("text-default", "surface-1"),
    ("text-muted", "surface-1"),
    ("success", "success-soft"),
    ("warning", "warning-soft"),
    ("danger", "danger-soft"),
    ("info", "info-soft"),
    ("violet", "violet-soft"),
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


def canonical_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def css_variables(block: str) -> dict[str, str]:
    return {
        match.group("name"): match.group("value").strip()
        for match in re.finditer(r"--(?P<name>[a-z0-9-]+)\s*:\s*(?P<value>[^;]+);", block)
    }


def color_channels(value: str) -> tuple[float, float, float]:
    if re.fullmatch(r"#[0-9a-fA-F]{6}", value) is None:
        raise ValueError(f"unsupported governed contrast color: {value}")
    return tuple(int(value[index : index + 2], 16) / 255 for index in (1, 3, 5))  # type: ignore[return-value]


def relative_luminance(value: str) -> float:
    channels = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in color_channels(value)
    ]
    return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722


def contrast_ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted((relative_luminance(foreground), relative_luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


class CatalogContractParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.class_counts: dict[str, int] = {}
        self.evidence_states: set[str] = set()
        self.uncertainty_states: set[str] = set()
        self.ids: dict[str, list[str]] = {}
        self.label_references: list[str] = []
        self._id_stack: list[str | None] = []

    def handle_starttag(self, tag: str, attributes: list[tuple[str, str | None]]) -> None:
        values = {name: value for name, value in attributes}
        for class_name in (values.get("class") or "").split():
            self.class_counts[class_name] = self.class_counts.get(class_name, 0) + 1
        evidence_state = values.get("data-evidence-state")
        if evidence_state:
            self.evidence_states.add(evidence_state)
        uncertainty_state = values.get("data-uncertainty-state")
        if uncertainty_state:
            self.uncertainty_states.add(uncertainty_state)
        element_id = values.get("id")
        if element_id:
            self.ids.setdefault(element_id, [])
        self._id_stack.append(element_id)
        labelledby = values.get("aria-labelledby")
        if labelledby:
            self.label_references.extend(labelledby.split())

    def handle_startendtag(self, tag: str, attributes: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attributes)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self._id_stack:
            self._id_stack.pop()

    def handle_data(self, data: str) -> None:
        for element_id in self._id_stack:
            if element_id:
                self.ids[element_id].append(data)


def catalog_contract_errors(catalog: str) -> list[str]:
    parser = CatalogContractParser()
    try:
        parser.feed(catalog)
        parser.close()
    except (TypeError, ValueError) as exc:
        return [f"desktop component catalog HTML cannot be parsed: {exc}"]
    errors: list[str] = []
    for marker in REQUIRED_COMPONENT_MARKERS:
        if parser.class_counts.get(marker, 0) == 0:
            errors.append(f"desktop component catalog has no structural {marker} instance")
    if parser.evidence_states != EXPECTED_EVIDENCE_STATES:
        errors.append("desktop component catalog must render every governed evidence state exactly by identity")
    if parser.uncertainty_states != EXPECTED_UNCERTAINTY_STATES:
        errors.append("desktop component catalog must render every governed uncertainty state exactly by identity")
    for reference in parser.label_references:
        targets = parser.ids.get(reference)
        if targets is None or not "".join(targets).strip():
            errors.append(f"desktop component catalog has a dangling or empty aria-labelledby target: {reference}")
    return errors


def component_style_errors(styles: str, components: str) -> list[str]:
    errors: list[str] = []
    uncommented_styles = re.sub(r"/\*.*?\*/", "", styles, flags=re.DOTALL)
    uncommented_components = re.sub(r"/\*.*?\*/|//[^\n]*", "", components, flags=re.DOTALL)
    for name in REQUIRED_COMPONENT_EXPORTS:
        if re.search(rf"(?m)^\s*export function {re.escape(name)}\s*\(", uncommented_components) is None:
            errors.append(f"desktop component package is missing exported {name}")
    for marker in REQUIRED_COMPONENT_MARKERS:
        if re.search(rf"\.{re.escape(marker)}(?![a-zA-Z0-9_-])", uncommented_styles) is None:
            errors.append(f"desktop component styles are missing structural selector .{marker}")
    if re.search(r"\bstyle\s*(?:=|:)", uncommented_components):
        errors.append("desktop component source must not bypass governed classes with inline styles")
    for match in re.finditer(r"(?P<property>[a-zA-Z-]+)\s*:\s*(?P<value>[^;{}]+)", uncommented_styles):
        property_name = match.group("property").lower()
        visual_properties = {
            "color",
            "background",
            "background-color",
            "fill",
            "stroke",
            "border",
            "outline",
            "box-shadow",
            "text-shadow",
        }
        if not (property_name in visual_properties or property_name.endswith("-color")):
            continue
        value = match.group("value").strip()
        remainder = re.sub(r"var\(--[a-z0-9-]+\)", "", value)
        allowed_value = r"(?:inherit|currentColor|solid|dashed|dotted|none|\d+(?:\.\d+)?(?:px|rem|em|%)?)"
        remainder = re.sub(allowed_value, "", remainder)
        if remainder.strip():
            errors.append(f"desktop component visual declaration must use governed tokens: {property_name}: {value}")
    return errors


def design_system_errors(repo: Path) -> list[str]:
    errors: list[str] = []
    tokens_path = repo / "design" / "ui-reference" / "assets" / "tokens.css"
    transport_path = repo / "packages" / "ui-tokens" / "index.css"
    contract_path = repo / "packages" / "ui-tokens" / "token-contract.json"
    component_path = repo / "packages" / "ui-components" / "src" / "index.tsx"
    styles_path = repo / "packages" / "ui-components" / "src" / "styles.css"
    catalog_path = repo / "packages" / "ui-components" / "catalog.html"
    component_manifest_path = repo / "packages" / "ui-components" / "package.json"
    lock_path = repo / "pnpm-lock.yaml"
    try:
        contract = json_object(contract_path)
        component_manifest = json_object(component_manifest_path)
        tokens = tokens_path.read_text(encoding="utf-8")
        transport = transport_path.read_text(encoding="utf-8")
        components = component_path.read_text(encoding="utf-8")
        styles = styles_path.read_text(encoding="utf-8")
        catalog = catalog_path.read_text(encoding="utf-8")
        lock = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        return [f"desktop design system cannot be loaded: {exc}"]
    if set(contract) != TOKEN_CONTRACT_KEYS or contract != EXPECTED_TOKEN_CONTRACT:
        errors.append("desktop token contract must exactly bind Academic Minimal 1.3")
    if canonical_sha256(tokens_path) != EXPECTED_TOKEN_CONTRACT["sourceCanonicalSha256"]:
        errors.append("desktop token source differs from its approved canonical SHA-256")
    if transport != EXPECTED_TOKEN_TRANSPORT:
        errors.append("desktop token transport must import only the governed reference source")
    errors.extend(component_style_errors(styles, components))
    errors.extend(catalog_contract_errors(catalog))
    if component_manifest.get("dependencies") != {"@research-observatory/ui-tokens": "workspace:*"}:
        errors.append("desktop component package must depend on the public ui-tokens workspace package")
    if component_manifest.get("peerDependencies") != {"react": "19.2.8"}:
        errors.append("desktop component package must declare its exact React peer contract")
    if component_manifest.get("sideEffects") != ["./src/styles.css"]:
        errors.append("desktop component package must preserve tree-shakeable style side-effect metadata")
    if 'from "@research-observatory/ui-tokens"' not in components or "../../ui-tokens" in components:
        errors.append("desktop components must consume ui-tokens through its public package API")
    importers = lock.get("importers") if isinstance(lock, dict) else None
    component_importer = importers.get("packages/ui-components") if isinstance(importers, dict) else None
    if not isinstance(component_importer, dict):
        errors.append("pnpm lockfile must contain the ui-components package importer")
    else:
        locked_dependencies = component_importer.get("dependencies")
        token_lock = (
            locked_dependencies.get("@research-observatory/ui-tokens")
            if isinstance(locked_dependencies, dict)
            else None
        )
        if token_lock != {"specifier": "workspace:*", "version": "link:../ui-tokens"}:
            errors.append("pnpm lockfile must bind ui-components to the public ui-tokens package")
        locked_development = component_importer.get("devDependencies")
        if not isinstance(locked_development, dict) or {
            "@types/react",
            "@types/react-dom",
            "react",
            "react-dom",
            "typescript",
            "vite",
            "vitest",
        } - set(locked_development):
            errors.append("pnpm lockfile must bind the ui-components standalone verification toolchain")
    root = re.search(r":root\s*\{(?P<body>.*?)\n\}", tokens, flags=re.DOTALL)
    dark = re.search(r'html\[data-theme="dark"\]\s*\{(?P<body>.*?)\n\}', tokens, flags=re.DOTALL)
    if root is None or dark is None:
        errors.append("desktop token source must define light and dark semantic scopes")
        return errors
    light_values = css_variables(root.group("body"))
    dark_values = {**light_values, **css_variables(dark.group("body"))}
    for theme, values in (("light", light_values), ("dark", dark_values)):
        for foreground, background in CONTRAST_PAIRS:
            try:
                ratio = contrast_ratio(values[foreground], values[background])
            except (KeyError, ValueError) as exc:
                errors.append(f"{theme} component contrast cannot be evaluated: {exc}")
                continue
            if ratio < 4.5:
                errors.append(f"{theme} {foreground}/{background} contrast is {ratio:.2f}, below WCAG AA")
    return errors


def component_catalog_browser_errors(repo: Path, browser_context: Any) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    details: dict[str, Any] = {"cases": 0, "themes": ["light", "dark"], "zoomPercent": [100, 150, 200]}
    try:
        html = (repo / "packages" / "ui-components" / "catalog.html").read_text(encoding="utf-8")
        tokens = (repo / "design" / "ui-reference" / "assets" / "tokens.css").read_text(encoding="utf-8")
        styles = (repo / "packages" / "ui-components" / "src" / "styles.css").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"desktop component catalog cannot be rendered: {exc}"], details
    catalog_layout = (
        "body{margin:0;padding:var(--space-4);color:var(--text-default);background:var(--canvas);"
        "font-family:var(--font-sans)}main{max-width:72rem;margin:auto}.catalog-grid{display:grid;"
        "grid-template-columns:repeat(auto-fit,minmax(min(18rem,100%),1fr));gap:var(--space-4);"
        "margin-block:var(--space-4)}"
    )
    document = html.replace("</head>", f"<style>{tokens}\n{styles}\n{catalog_layout}</style></head>")
    for theme in ("light", "dark"):
        for zoom_percent in (100, 150, 200):
            page = browser_context.new_page()
            page.set_viewport_size({"width": 1280, "height": 720})
            try:
                page.set_content(document, wait_until="load")
                page.evaluate(
                    """
                    ([theme, zoom]) => {
                      document.documentElement.dataset.theme = theme;
                      document.documentElement.style.zoom = String(zoom);
                    }
                    """,
                    [theme, zoom_percent / 100],
                )
                catalog_script = """
                    () => ({
                      catalog: document.querySelector('[data-component-catalog]')
                        ?.getAttribute('data-component-catalog'),
                      overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                      minimumControl: Math.min(
                        ...Array.from(document.querySelectorAll('button,input'))
                          .map((node) => node.getBoundingClientRect().height)
                      ),
                      alertCount: document.querySelectorAll('[role=alert]').length,
                      statusCount: document.querySelectorAll('[role=status]').length,
                      dialogName: document.querySelector('dialog')?.getAttribute('aria-labelledby'),
                      dialogTargetCount: (() => {
                        const reference = document.querySelector('dialog')?.getAttribute('aria-labelledby');
                        return reference ? document.querySelectorAll(`#${CSS.escape(reference)}`).length : 0;
                      })(),
                      dialogTargetText: (() => {
                        const reference = document.querySelector('dialog')?.getAttribute('aria-labelledby');
                        return reference ? document.getElementById(reference)?.textContent?.trim() : '';
                      })(),
                      componentCounts: Object.fromEntries(__REQUIRED_COMPONENT_MARKERS__.map(
                        (className) => [className, document.getElementsByClassName(className).length]
                      )),
                      evidenceStates: Array.from(document.querySelectorAll('[data-evidence-state]'))
                        .map((node) => node.getAttribute('data-evidence-state')),
                      uncertaintyStates: Array.from(document.querySelectorAll('[data-uncertainty-state]'))
                        .map((node) => node.getAttribute('data-uncertainty-state')),
                    })
                    """.replace("__REQUIRED_COMPONENT_MARKERS__", json.dumps(list(REQUIRED_COMPONENT_MARKERS)))
                observed = page.evaluate(catalog_script)
                if observed.get("catalog") != "1.0.0" or observed.get("overflow") is not False:
                    errors.append(f"{theme} {zoom_percent}% component catalog identity or horizontal fit failed")
                if float(observed.get("minimumControl") or 0) < 40 * zoom_percent / 100:
                    errors.append(f"{theme} {zoom_percent}% component controls are below their approved minimum")
                if (
                    observed.get("alertCount") != 1
                    or observed.get("statusCount") != 2
                    or not observed.get("dialogName")
                    or observed.get("dialogTargetCount") != 1
                    or not observed.get("dialogTargetText")
                ):
                    errors.append(f"{theme} {zoom_percent}% component semantics are incomplete")
                component_counts = observed.get("componentCounts")
                if not isinstance(component_counts, dict) or any(
                    component_counts.get(marker, 0) < 1 for marker in REQUIRED_COMPONENT_MARKERS
                ):
                    errors.append(f"{theme} {zoom_percent}% component structural inventory is incomplete")
                if set(observed.get("evidenceStates") or []) != EXPECTED_EVIDENCE_STATES:
                    errors.append(f"{theme} {zoom_percent}% component evidence-state inventory is incomplete")
                if set(observed.get("uncertaintyStates") or []) != EXPECTED_UNCERTAINTY_STATES:
                    errors.append(f"{theme} {zoom_percent}% component uncertainty-state inventory is incomplete")
                details["cases"] += 1
            except PlaywrightError as exc:
                errors.append(f"{theme} {zoom_percent}% component catalog browser check failed: {exc}")
            finally:
                page.close()
    return errors, details


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
    environment["CI"] = "true"
    environment["PATH"] = os.pathsep.join((str(node_root), str(cargo.parent), environment.get("PATH", "")))
    environment["COREPACK_HOME"] = str(repo / ".local" / "toolchains" / "corepack")
    environment["CARGO_HOME"] = str(cargo_root)
    environment["RUSTUP_HOME"] = str(repo / ".local" / "toolchains" / "rustup")
    return environment, corepack, cargo


def command_plan(repo: Path) -> list[list[str]]:
    _, corepack, cargo = tool_environment(repo)
    app = str(repo / "apps" / "desktop")
    component_package = str(repo / "packages" / "ui-components")
    return [
        [str(corepack), "pnpm", "--dir", component_package, "verify"],
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
        "projectSelection": {
            "recentProjects": 0,
            "missingProjects": 0,
            "persistentRemoval": False,
            "emptyState": False,
            "preferenceRecovery": False,
            "writeFailurePreserved": False,
            "intents": [],
        },
        "keyboardRail": False,
        "commandFocus": False,
        "requests": [],
        "designSystem": {},
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
            catalog_errors, catalog_details = component_catalog_browser_errors(repo, browser_context)
            errors.extend(catalog_errors)
            details["designSystem"] = catalog_details
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
            project_page = browser_context.new_page()
            project_page.add_init_script(
                """
                window.__projectIntents = [];
                document.addEventListener("research-observatory:project-intent", (event) => {
                  window.__projectIntents.push(event.detail);
                  event.preventDefault();
                });
                """
            )
            projects_url = "http://tauri.localhost/projects.html"
            project_page.goto(projects_url, wait_until="load")
            project_page.wait_for_function("document.body.dataset.projectSelection === 'ready'", timeout=5_000)
            project_details = details["projectSelection"]
            recent = project_page.locator("[data-recent-project-id]")
            project_details["recentProjects"] = recent.count()
            project_details["missingProjects"] = project_page.locator('[data-project-availability="missing"]').count()
            expected_ids = [
                "generative-ai-creative-cognition",
                "community-governed-ai",
                "recurrent-staged-loras",
                "digital-control-worker-autonomy",
            ]
            observed_ids = recent.evaluate_all("nodes => nodes.map(node => node.dataset.recentProjectId)")
            if observed_ids != expected_ids:
                errors.append(f"project recents were not deterministic: {observed_ids}")

            missing = project_page.locator('[data-project-availability="missing"]')
            missing.locator('[data-project-action="locate-existing"]').click()
            if project_page.url != projects_url:
                errors.append("missing-project locate action navigated away from the existing project")
            intents = project_page.evaluate("window.__projectIntents")
            if intents != [{"type": "locate-existing", "projectId": "recurrent-staged-loras"}]:
                errors.append(f"missing-project repair emitted unexpected intents: {intents}")

            available = project_page.locator('[data-project-availability="available"]').first
            available.locator('[data-project-action="open-existing"]').click()
            if project_page.url != projects_url:
                errors.append(
                    "handled existing-project open intent navigated before the project authority completed it"
                )

            missing.locator('[data-project-action="remove-recent"]').click()
            stored = project_page.evaluate("localStorage.getItem('research-observatory.project-recents.v1')")
            if stored != '{"schemaVersion":1,"removedProjectIds":["recurrent-staged-loras"]}':
                errors.append(f"recent-project removal was not canonical: {stored!r}")
            project_details["intents"] = project_page.evaluate("window.__projectIntents")
            project_page.reload(wait_until="load")
            project_page.wait_for_function("document.body.dataset.projectSelection === 'ready'", timeout=5_000)
            if project_page.locator('[data-recent-project-id="recurrent-staged-loras"]').count() == 0:
                project_details["persistentRemoval"] = True

            while project_page.locator("[data-recent-project-id]").count():
                project_page.locator("[data-recent-project-id]").first.locator(
                    '[data-project-action="remove-recent"]'
                ).click()
            project_details["emptyState"] = (
                project_page.locator('[data-project-empty-state="ready"] a[href="new-project.html"]').count() == 1
                and project_page.locator("body").get_attribute("data-recent-project-count") == "0"
            )
            project_page.locator('[data-project-empty-state="ready"] a[href="new-project.html"]').click()
            project_page.wait_for_function("document.body.dataset.projectSelection === 'ready'", timeout=5_000)
            if project_page.url != "http://tauri.localhost/new-project.html":
                errors.append("empty project state did not open the explicit new-project flow")
            project_page.locator('[data-project-action="create-new"]').click()
            if project_page.url != "http://tauri.localhost/new-project.html":
                errors.append(
                    "handled explicit project-creation intent navigated before project authority completed it"
                )
            project_details["intents"].extend(project_page.evaluate("window.__projectIntents"))

            project_page.evaluate(
                "localStorage.setItem('research-observatory.project-recents.v1', "
                '\'{"schemaVersion":2,"removedProjectIds":[]}\')'
            )
            project_page.goto(projects_url, wait_until="load")
            project_page.wait_for_function("document.body.dataset.projectSelection === 'ready'", timeout=5_000)
            recovery_status = project_page.locator('[data-project-selection-status="recovery"]')
            raw_after_recovery = project_page.evaluate(
                "localStorage.getItem('research-observatory.project-recents.v1')"
            )
            project_details["preferenceRecovery"] = (
                recovery_status.count() == 1
                and not recovery_status.is_hidden()
                and raw_after_recovery == '{"schemaVersion":2,"removedProjectIds":[]}'
                and project_page.locator("[data-recent-project-id]").count() == 4
            )
            project_page.close()

            write_failure_page = browser_context.new_page()
            write_failure_page.add_init_script(
                """
                Storage.prototype.setItem = () => { throw new Error("controlled preference write failure"); };
                """
            )
            write_failure_page.goto(projects_url, wait_until="load")
            write_failure_page.wait_for_function("document.body.dataset.projectSelection === 'ready'", timeout=5_000)
            before_failure = write_failure_page.locator("[data-recent-project-id]").count()
            write_failure_page.locator('[data-project-action="remove-recent"]').first.click()
            error_status = write_failure_page.locator('[data-project-selection-status="error"]')
            project_details["writeFailurePreserved"] = (
                write_failure_page.locator("[data-recent-project-id]").count() == before_failure
                and error_status.count() == 1
                and not error_status.is_hidden()
            )
            write_failure_page.close()
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
    project_details = details["projectSelection"]
    if project_details.get("recentProjects") != 4 or project_details.get("missingProjects") != 1:
        errors.append("desktop project selection did not expose the deterministic recent/missing fixture")
    for field in ("persistentRemoval", "emptyState", "preferenceRecovery", "writeFailurePreserved"):
        if project_details.get(field) is not True:
            errors.append(f"desktop project selection did not verify {field}")
    return errors, details


def validate(repo: Path, runner: Runner = subprocess.run) -> dict[str, Any]:
    errors = [*security_errors(repo), *design_system_errors(repo)]
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
