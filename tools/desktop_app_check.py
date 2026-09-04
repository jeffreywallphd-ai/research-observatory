#!/usr/bin/env python3
"""Build and validate the pinned offline Tauri/React desktop application."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import yaml
from bs4 import BeautifulSoup
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright
from ui_conformance import confined_path, file_inventory, load_context, stable_file_bytes

Runner = Callable[..., subprocess.CompletedProcess[str]]
PRODUCT_ROOT = "apps/desktop/product-dist"
PRODUCT_MANIFEST = f"{PRODUCT_ROOT}/application-manifest.json"
PRODUCT_MANIFEST_KEYS = {
    "schemaVersion",
    "documentType",
    "buildRole",
    "implementedCapabilities",
    "routes",
    "referenceUse",
    "referenceId",
    "referencePackageSha256",
    "sourceFiles",
    "artifacts",
}
PRODUCT_EXTERNAL_INPUTS = (
    "Cargo.toml",
    "Cargo.lock",
    "package.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    "verification/extensions/desktop-ui.json",
)
PRODUCT_PACKAGE_ROOTS = (
    "packages/ui-components",
    "packages/ui-tokens",
)
PRODUCT_EXCLUDED_DIRECTORIES = frozenset({"dist", "product-dist", "node_modules", "target"})
DATA_TABLE_INTERACTIVE_RUNNER = "tests/desktop/fixtures/data-table-interactive.mjs"
NODE_RUNTIME = ".local/toolchains/node-v24.19.0-win-x64/node.exe"
EXPECTED_PRODUCT_ARTIFACTS = {
    "assets/app.css",
    "assets/app.js",
    "assets/app.js.map",
    "index.html",
}
REFERENCE_ONLY_MARKERS = (
    "prototype-index.html",
    "style-guide.html",
    "data-workflow-select",
)
IMPLEMENTED_PRODUCT_PAGE_CONTRACTS = frozenset(
    {
        "application-settings.html",
        "audit-lineage.html",
        "help-onboarding.html",
        "index.html",
        "intent-contract.html",
        "new-project.html",
        "project-settings.html",
        "projects.html",
        "task-center.html",
    }
)
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
EXPECTED_MAIN_WINDOW_PERMISSIONS = (
    "core:webview:allow-internal-toggle-devtools",
    "core:event:allow-listen",
    "core:event:allow-unlisten",
)
EXPECTED_MAIN_WINDOW_CAPABILITY_FIELDS = {
    "$schema",
    "identifier",
    "description",
    "windows",
    "permissions",
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
    "referenceId": "RO-UI-ACADEMIC-MINIMAL-1.4",
    "referenceVersion": "1.4",
    "referencePackageSha256": "034d592ea97c35113ac802f885a469f89f9c72ad2548740347bef00f7484310e",
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
    "ro-boundary-state",
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
    "BoundaryStatePanel",
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
EXPECTED_BOUNDARY_STATES = {
    "loading",
    "empty",
    "offline",
    "denied",
    "stale",
    "partial",
    "failed",
    "recovery-required",
}
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


def payload_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def product_build_errors(repo: Path) -> list[str]:
    """Verify the functional Tauri bundle independently from the reference fixture."""
    repo = repo.resolve(strict=True)
    errors: list[str] = []
    try:
        product_root = confined_path(repo, PRODUCT_ROOT)
        manifest_path = confined_path(repo, PRODUCT_MANIFEST)
        manifest_payload = stable_file_bytes(repo, manifest_path)
        manifest = json.loads(manifest_payload.decode("utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("desktop product manifest must contain an object")
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        return [f"desktop product bundle cannot be loaded: {exc}"]

    if set(manifest) != PRODUCT_MANIFEST_KEYS:
        return ["desktop product manifest has a noncanonical field set"]
    expected_identity = {
        "schemaVersion": "1.0",
        "documentType": "desktop-product-build-manifest",
        "buildRole": "tauri-frontend",
        "implementedCapabilities": [
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
        "routes": ["index.html"],
        "referenceUse": "design-contract-only",
    }
    for field, expected in expected_identity.items():
        if manifest.get(field) != expected:
            errors.append(f"desktop product manifest {field} must equal {expected!r}")

    try:
        application_root = confined_path(repo, "apps/desktop")
        expected_sources = file_inventory(repo, application_root, excluded_directories=PRODUCT_EXCLUDED_DIRECTORIES)
        for relative in PRODUCT_PACKAGE_ROOTS:
            package_root = confined_path(repo, relative)
            expected_sources.update(
                file_inventory(repo, package_root, excluded_directories=PRODUCT_EXCLUDED_DIRECTORIES)
            )
        for relative in PRODUCT_EXTERNAL_INPUTS:
            expected_sources[relative] = payload_sha256(stable_file_bytes(repo, confined_path(repo, relative)))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return [f"desktop product source inventory cannot be loaded: {exc}"]
    if manifest.get("sourceFiles") != dict(sorted(expected_sources.items())):
        errors.append("desktop product manifest does not bind the exact product build inputs")

    artifact_inventory = file_inventory(repo, product_root)
    manifest_relative = manifest_path.relative_to(repo).as_posix()
    artifact_inventory.pop(manifest_relative, None)
    expected_artifacts = {
        Path(relative).relative_to(product_root.relative_to(repo)).as_posix(): digest
        for relative, digest in artifact_inventory.items()
    }
    if set(expected_artifacts) != EXPECTED_PRODUCT_ARTIFACTS:
        errors.append(
            "desktop product bundle must contain only the functional index/runtime inventory: "
            f"found={sorted(expected_artifacts)}"
        )
    if manifest.get("artifacts") != dict(sorted(expected_artifacts.items())):
        errors.append("desktop product manifest does not bind the exact product artifacts")

    try:
        tauri = json.loads(stable_file_bytes(repo, confined_path(repo, "apps/desktop/src-tauri/tauri.conf.json")))
        index = stable_file_bytes(repo, confined_path(product_root, "index.html")).decode("utf-8")
        reference_site = json.loads(
            stable_file_bytes(repo, confined_path(repo, "design/ui-reference/SITE_MANIFEST.json"))
        )
        activation = json.loads(stable_file_bytes(repo, confined_path(repo, "verification/extensions/desktop-ui.json")))
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"desktop product/reference boundary cannot be loaded: {exc}")
        return errors
    if tauri.get("build", {}).get("frontendDist") != "../product-dist":
        errors.append("Tauri production and development must serve only apps/desktop/product-dist")
    if manifest.get("referenceId") != activation.get("referenceId") or manifest.get(
        "referencePackageSha256"
    ) != activation.get("referencePackageSha256"):
        errors.append("desktop product manifest does not bind the approved design reference identity")
    reference_pages = {item.get("file") for item in reference_site.get("pages", []) if isinstance(item, dict)}
    leaked_pages = sorted((set(expected_artifacts) & reference_pages) - {"index.html"})
    if leaked_pages:
        errors.append(f"reference-only pages entered the desktop product bundle: {leaked_pages}")
    leaked_markers = sorted(marker for marker in REFERENCE_ONLY_MARKERS if marker in index)
    if leaked_markers:
        errors.append(f"reference-only markers entered the desktop product HTML: {leaked_markers}")
    text_artifacts = "\n".join(
        stable_file_bytes(repo, confined_path(product_root, relative)).decode("utf-8", errors="replace")
        for relative in sorted(EXPECTED_PRODUCT_ARTIFACTS)
    )
    leaked_route_names = sorted(
        page
        for page in reference_pages - IMPLEMENTED_PRODUCT_PAGE_CONTRACTS
        if isinstance(page, str) and page in text_artifacts
    )
    if leaked_route_names:
        errors.append(f"reference-only routes entered the desktop product runtime: {leaked_route_names}")
    return errors


def inline_product_index(repo: Path) -> str:
    """Embed the exact local product CSS and module for offline browser checks."""
    repo = repo.resolve(strict=True)
    root = confined_path(repo, PRODUCT_ROOT)
    document = BeautifulSoup(confined_path(root, "index.html").read_text(encoding="utf-8"), "html.parser")
    if document.html is None or document.head is None or document.body is None:
        raise ValueError("desktop product index must be a complete HTML document")
    for tag in list(document.find_all("link", rel="stylesheet")):
        tag.decompose()
    for tag in list(document.find_all("script", src=True)):
        tag.decompose()
    style = document.new_tag("style")
    style.string = confined_path(root, "assets/app.css").read_text(encoding="utf-8")
    document.head.append(style)
    script = document.new_tag("script", type="module")
    script.string = confined_path(root, "assets/app.js").read_text(encoding="utf-8")
    document.body.append(script)
    return str(document)


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
        self.boundary_states: list[str] = []
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
        boundary_state = values.get("data-boundary-state")
        if boundary_state:
            self.boundary_states.append(boundary_state)
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
    if set(parser.boundary_states) != EXPECTED_BOUNDARY_STATES or len(parser.boundary_states) != len(
        EXPECTED_BOUNDARY_STATES
    ):
        errors.append("desktop component catalog must render every governed boundary state exactly by identity")
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
                      boundaryStates: Array.from(document.querySelectorAll('[data-boundary-state]'))
                        .map((node) => node.getAttribute('data-boundary-state')),
                    })
                    """.replace("__REQUIRED_COMPONENT_MARKERS__", json.dumps(list(REQUIRED_COMPONENT_MARKERS)))
                observed = page.evaluate(catalog_script)
                if observed.get("catalog") != "1.2.0" or observed.get("overflow") is not False:
                    errors.append(f"{theme} {zoom_percent}% component catalog identity or horizontal fit failed")
                if float(observed.get("minimumControl") or 0) < 40 * zoom_percent / 100:
                    errors.append(f"{theme} {zoom_percent}% component controls are below their approved minimum")
                if (
                    observed.get("alertCount") != 4
                    or observed.get("statusCount") != 7
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
                if set(observed.get("boundaryStates") or []) != EXPECTED_BOUNDARY_STATES or len(
                    observed.get("boundaryStates") or []
                ) != len(EXPECTED_BOUNDARY_STATES):
                    errors.append(f"{theme} {zoom_percent}% component boundary-state inventory is incomplete")
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
    if not isinstance(build, dict) or build.get("frontendDist") != "../product-dist" or "devUrl" in build:
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
    permissions = capability.get("permissions")
    if (
        set(capability) != EXPECTED_MAIN_WINDOW_CAPABILITY_FIELDS
        or capability.get("identifier") != "main-window"
        or capability.get("windows") != ["main"]
        or not isinstance(permissions, list)
        or tuple(permissions) != EXPECTED_MAIN_WINDOW_PERMISSIONS
    ):
        errors.append(
            "the desktop capability must grant exactly the receive-only event permissions "
            "and the narrow WebView inspector toggle command"
        )
    generated_capabilities = json_object(
        repo / "apps" / "desktop" / "src-tauri" / "gen" / "schemas" / "capabilities.json"
    )
    expected_generated = {
        "main-window": {
            "identifier": capability.get("identifier"),
            "description": capability.get("description"),
            "local": True,
            "windows": capability.get("windows"),
            "permissions": capability.get("permissions"),
        }
    }
    if generated_capabilities != expected_generated:
        errors.append("the generated Tauri capability projection must exactly match the reviewed source capability")
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
        [str(corepack), "pnpm", "--dir", component_package, "run", "verify"],
        [str(corepack), "pnpm", "--dir", app, "run", "lint"],
        [str(corepack), "pnpm", "--dir", app, "run", "typecheck"],
        [str(corepack), "pnpm", "--dir", app, "run", "test"],
        [str(corepack), "pnpm", "--dir", app, "run", "build"],
        [str(cargo), "fmt", "--all", "--check"],
        [str(cargo), "clippy", "--workspace", "--all-targets", "--locked", "--", "-D", "warnings"],
        [str(cargo), "test", "--workspace", "--locked"],
        [str(cargo), "build", "--workspace", "--locked"],
    ]


def page_error_collector(target: list[str]) -> Callable[[PlaywrightError], None]:
    def collect(error: PlaywrightError) -> None:
        target.append(str(error))

    return collect


def data_table_interaction_errors(repo: Path, browser_context: Any) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    details: dict[str, Any] = {
        "totalRows": 10_000,
        "maximumRenderedRows": 0,
        "pageSize": 50,
        "pages": 200,
        "keyboardTransitions": False,
        "focusPreserved": False,
        "disabledBoundaries": False,
        "compact": False,
    }
    node = repo / NODE_RUNTIME
    runner = repo / DATA_TABLE_INTERACTIVE_RUNNER
    if not node.is_file() or not runner.is_file():
        return ["interactive DataTable verifier requires the pinned Node runtime and test fixture"], details

    with tempfile.TemporaryDirectory(prefix="ro-data-table-interactive-") as temporary:
        output_root = Path(temporary)
        completed = subprocess.run(
            [str(node), str(runner), str(output_root)],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        if completed.returncode:
            diagnostic = (completed.stderr or completed.stdout).strip()
            return [f"interactive DataTable fixture build failed: {diagnostic}"], details
        bundle = output_root / "data-table-interactive.js"
        if not bundle.is_file():
            return ["interactive DataTable fixture build omitted its exact browser bundle"], details

        page = browser_context.new_page()
        page_errors: list[str] = []
        page.on("pageerror", page_error_collector(page_errors))
        try:
            page.set_content('<!doctype html><html><body><main><div id="root"></div></main></body></html>')
            page.add_script_tag(content=bundle.read_text(encoding="utf-8"))
            page.wait_for_function("document.body.dataset.tableHarnessReady === 'true'", timeout=5_000)
            table = page.locator(".ro-data-table")
            rows = table.locator("tbody tr")
            status = table.locator('[aria-live="polite"]')
            previous = table.get_by_role("button", name="Previous page of 10,000-row interactive inventory")
            following = table.get_by_role("button", name="Next page of 10,000-row interactive inventory")

            details["maximumRenderedRows"] = rows.count()
            details["compact"] = table.locator('table[data-density="compact"]').count() == 1
            first_valid = (
                table.get_attribute("data-total-rows") == "10000"
                and table.get_attribute("data-rendered-rows") == "50"
                and rows.count() == 50
                and status.inner_text().strip() == "Rows 1-50 of 10000. Page 1 of 200."
                and "Research record 0" in table.inner_text()
                and "Research record 49" in table.inner_text()
                and "Research record 50" not in table.inner_text()
                and previous.is_disabled()
                and following.is_enabled()
            )

            following.focus()
            following.press("Enter")
            page.wait_for_function(
                "document.querySelector('[aria-live=polite]')?.textContent?.includes('Rows 51-100 of 10000')"
            )
            next_focus = page.evaluate(
                "document.activeElement?.getAttribute('aria-label') === 'Next page of 10,000-row interactive inventory'"
            )
            for _index in range(198):
                following.click()
            page.wait_for_function(
                "document.querySelector('[aria-live=polite]')?.textContent?.includes('Page 200 of 200')"
            )
            last_text = table.inner_text()
            last_valid = (
                rows.count() == 50
                and status.inner_text().strip() == "Rows 9951-10000 of 10000. Page 200 of 200."
                and "Research record 9950" in last_text
                and "Research record 9999" in last_text
                and "Research record 9949" not in last_text
                and following.is_disabled()
                and previous.is_enabled()
            )

            previous.focus()
            previous.press("Enter")
            page.wait_for_function(
                "document.querySelector('[aria-live=polite]')?.textContent?.includes('Rows 9901-9950 of 10000')"
            )
            previous_focus = page.evaluate(
                "document.activeElement?.getAttribute('aria-label') === "
                "'Previous page of 10,000-row interactive inventory'"
            )
            for _index in range(198):
                previous.click()
            page.wait_for_function(
                "document.querySelector('[aria-live=polite]')?.textContent?.includes('Page 1 of 200')"
            )
            returned_valid = (
                rows.count() == 50
                and status.inner_text().strip() == "Rows 1-50 of 10000. Page 1 of 200."
                and previous.is_disabled()
                and following.is_enabled()
            )
            details["keyboardTransitions"] = first_valid and last_valid and returned_valid
            details["focusPreserved"] = next_focus and previous_focus
            details["disabledBoundaries"] = first_valid and last_valid and returned_valid
            if page_errors:
                errors.append(f"interactive DataTable runtime error: {'; '.join(page_errors)}")
        except (OSError, PlaywrightError, ValueError) as exc:
            errors.append(f"interactive DataTable browser check failed: {exc}")
        finally:
            page.close()

    for field in ("keyboardTransitions", "focusPreserved", "disabledBoundaries", "compact"):
        if details[field] is not True:
            errors.append(f"interactive 10,000-row DataTable did not verify {field}")
    if details["maximumRenderedRows"] != 50:
        errors.append("interactive 10,000-row DataTable exceeded its 50-row render bound")
    return errors, details


def core_workflow_catalog_json(repo: Path) -> str:
    catalog_process = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from research_observatory_core.projects import ProjectLifecycleService; "
                "from research_observatory_core.research_intents import ResearchIntentService; "
                "print(ResearchIntentService.unavailable(ProjectLifecycleService())"
                ".workflow_profile_catalog().model_dump_json(by_alias=True))"
            ),
        ],
        cwd=repo,
        env={**os.environ, "PYTHONPATH": str(repo / "services" / "core-api" / "src")},
        capture_output=True,
        text=True,
        check=False,
    )
    if catalog_process.returncode != 0:
        raise ValueError("desktop workflow catalog fixture could not be projected by Core")
    workflow_catalog_json = catalog_process.stdout.strip()
    try:
        json.loads(workflow_catalog_json)
    except json.JSONDecodeError as error:
        raise ValueError("desktop workflow catalog fixture was not canonical JSON") from error
    return workflow_catalog_json


def runtime_frame_errors(repo: Path) -> tuple[list[str], dict[str, Any]]:
    errors = product_build_errors(repo)
    runtime_path = repo / PRODUCT_ROOT / "assets" / "app.js"
    runtime = runtime_path.read_text(encoding="utf-8") if runtime_path.is_file() else ""
    if "process.env.NODE_ENV" in runtime:
        errors.append("desktop production runtime retains an unresolved Node environment expression")
    details: dict[str, Any] = {
        "pages": 0,
        "implementedCapabilities": [
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
        "referenceOnlyPages": 0,
        "commandFocus": False,
        "skipLink": False,
        "shortcutDialog": False,
        "focusContainment": False,
        "focusRestoration": False,
        "focusVisible": False,
        "keyboardCommand": False,
        "homeShortcut": False,
        "themeToggle": False,
        "liveRegion": False,
        "boundaryState": False,
        "boundaryRecovery": False,
        "retainedInput": False,
        "diagnosticCopy": False,
        "diagnosticsUnavailable": False,
        "diagnosticsPreview": False,
        "diagnosticsTraceLink": False,
        "diagnosticsExactExport": False,
        "projectsWorkflow": False,
        "workflowProfileMatrixValid": False,
        "workflowProfileMatrix": {},
        "workflowEarlierStageRevisit": False,
        "adaptiveWorkflowNavigation": False,
        "intentMutationRaceGuarded": False,
        "privacySettingsWorkflow": False,
        "applicationLock": False,
        "applicationLockEventAclStartup": False,
        "applicationLockEventAclStartupCases": {},
        "applicationLockReconciliation": False,
        "applicationSettingsDraftReconciliation": False,
        "applicationSettingsConflictAnnouncement": False,
        "applicationSettingsPositionPreserved": False,
        "intentStoppingEffects": False,
        "applicationSettingsFocusRestoration": False,
        "applicationHelloRecovery": False,
        "responsiveCases": 0,
        "criticalViolations": [],
        "requests": [],
        "designSystem": {},
        "largeTable": {},
    }
    if errors:
        return errors, details
    document = inline_product_index(repo)
    try:
        workflow_catalog_json = core_workflow_catalog_json(repo)
    except ValueError as error:
        return [*errors, str(error)], details
    workflow_catalog = json.loads(workflow_catalog_json)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        browser_context = browser.new_context()

        def serve_application(route: Any) -> None:
            if route.request.url in {"http://tauri.localhost/", "http://tauri.localhost/index.html"}:
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=document)
            else:
                details["requests"].append(route.request.url)
                route.abort()

        def open_desktop_tool(page: Any, name: str) -> None:
            disclosure = page.locator("[data-all-tools]")
            if disclosure.get_attribute("open") is None:
                disclosure.locator("summary").click()
            disclosure.get_by_role("button", name=name, exact=True).click()

        browser_context.route("**/*", serve_application)
        try:
            catalog_errors, catalog_details = component_catalog_browser_errors(repo, browser_context)
            errors.extend(catalog_errors)
            details["designSystem"] = catalog_details
            table_errors, table_details = data_table_interaction_errors(repo, browser_context)
            errors.extend(table_errors)
            details["largeTable"] = table_details
            page = browser_context.new_page()
            page_errors: list[str] = []
            page.on("pageerror", page_error_collector(page_errors))
            page.goto("http://tauri.localhost/index.html", wait_until="load")
            page.wait_for_function("document.body.dataset.applicationReady === 'true'", timeout=5_000)
            details["pages"] = 1
            details["referenceOnlyPages"] = page.locator('a[href$=".html"], [data-workflow-select]').count()
            violations = page.evaluate(
                r"""() => {
                  const violations = [];
                  const ids = Array.from(document.querySelectorAll('[id]')).map((node) => node.id);
                  const duplicates = [...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))];
                  if (duplicates.length) violations.push(`duplicate ids: ${duplicates.join(',')}`);
                  for (const node of document.querySelectorAll('[aria-labelledby]')) {
                    for (const id of node.getAttribute('aria-labelledby').split(/\s+/)) {
                      if (!document.getElementById(id)?.textContent?.trim()) violations.push(`dangling label: ${id}`);
                    }
                  }
                  for (const node of document.querySelectorAll('a[href],button,input')) {
                    const name = node.getAttribute('aria-label') || node.textContent?.trim()
                      || node.labels?.[0]?.textContent?.trim() || node.getAttribute('value')
                      || node.getAttribute('placeholder');
                    if (!name) violations.push(`unnamed interactive: ${node.tagName}`);
                  }
                  if (document.querySelectorAll('h1').length !== 1) violations.push('application requires one h1');
                  if (!document.querySelector('header') || !document.querySelector('nav')
                    || !document.querySelector('main') || !document.querySelector('footer')) {
                    violations.push('application landmarks are incomplete');
                  }
                  return violations;
                }"""
            )
            details["criticalViolations"] = violations
            errors.extend(f"desktop accessibility violation: {violation}" for violation in violations)

            page.locator("body").focus()
            page.keyboard.press("Tab")
            details["skipLink"] = page.evaluate("document.activeElement?.classList.contains('skip-link') === true")
            page.keyboard.press("Enter")
            details["skipLink"] = details["skipLink"] and page.evaluate("document.activeElement?.id === 'main-content'")

            page.keyboard.press("Control+K")
            page.wait_for_function("document.activeElement?.id === 'shell-command'", timeout=5_000)
            details["commandFocus"] = page.evaluate("document.activeElement?.id === 'shell-command'")
            details["focusVisible"] = page.evaluate(
                "parseFloat(getComputedStyle(document.activeElement).outlineWidth) >= 2"
            )
            page.keyboard.press("Control+/")
            page.locator('[role="dialog"]').wait_for(state="visible", timeout=5_000)
            details["shortcutDialog"] = page.locator('[role="dialog"][aria-modal="true"]').count() == 1
            details["shortcutDialog"] = details["shortcutDialog"] and page.evaluate(
                "document.activeElement?.textContent?.trim() === 'Close shortcuts'"
            )
            dialog_name_valid = page.evaluate(
                """() => {
                  const dialog = document.querySelector('[role="dialog"]');
                  const id = dialog?.getAttribute('aria-labelledby');
                  return Boolean(id && document.getElementById(id)?.textContent?.trim());
                }"""
            )
            if not dialog_name_valid:
                violations.append("shortcut dialog lacks a resolvable accessible name")
                errors.append("desktop accessibility violation: shortcut dialog lacks a resolvable accessible name")
            page.keyboard.press("Tab")
            details["focusContainment"] = page.evaluate(
                "document.activeElement?.textContent?.trim() === 'Close shortcuts'"
            )
            page.keyboard.press("Shift+Tab")
            details["focusContainment"] = details["focusContainment"] and page.evaluate(
                "document.activeElement?.textContent?.trim() === 'Close shortcuts'"
            )
            for shortcut in ("Control+K", "Control+/", "Alt+H", "Control+/"):
                page.keyboard.press(shortcut)
                details["focusContainment"] = details["focusContainment"] and page.evaluate(
                    """() => {
                      const dialog = document.querySelector('[role="dialog"][aria-modal="true"]');
                      return Boolean(dialog && dialog.contains(document.activeElement)
                        && document.activeElement?.textContent?.trim() === 'Close shortcuts');
                    }"""
                )
            page.keyboard.press("Escape")
            page.wait_for_function("document.activeElement?.id === 'shell-command'", timeout=5_000)
            details["focusRestoration"] = page.locator('[role="dialog"]').count() == 0 and page.evaluate(
                "document.activeElement?.id === 'shell-command'"
            )
            page.keyboard.press("Alt+H")
            page.wait_for_function("document.activeElement?.id === 'main-content'", timeout=5_000)
            details["homeShortcut"] = page.evaluate("document.activeElement?.id === 'main-content'")

            theme_toggle = page.locator("[data-theme-toggle]")
            previous_theme = page.locator("html").get_attribute("data-theme")
            initial_toggle_name = theme_toggle.inner_text().strip()
            initial_pressed = theme_toggle.get_attribute("aria-pressed")
            theme_toggle.focus()
            page.keyboard.press("Enter")
            current_theme = page.locator("html").get_attribute("data-theme")
            details["themeToggle"] = (
                current_theme != previous_theme
                and initial_toggle_name == "Dark theme"
                and theme_toggle.inner_text().strip() == initial_toggle_name
                and initial_pressed == ("true" if previous_theme == "dark" else "false")
                and theme_toggle.get_attribute("aria-pressed") == ("true" if current_theme == "dark" else "false")
            )
            details["keyboardCommand"] = details["themeToggle"]
            page.wait_for_function(
                "document.querySelector('[data-live-region]')?.textContent?.includes('theme active')",
                timeout=5_000,
            )
            details["liveRegion"] = (
                page.locator("[data-live-region]").get_attribute("aria-live") == "polite"
                and "theme active" in page.locator("[data-live-region]").inner_text()
            )
            command = page.locator("#shell-command")
            command.fill("Retained local draft")
            boundary = page.locator("[data-local-service-boundary]")
            diagnostic = boundary.locator("[data-diagnostic-reference]").inner_text().strip()
            details["boundaryState"] = (
                boundary.get_attribute("data-boundary-state") == "recovery-required"
                and diagnostic == "RO-CORE-SUPERVISOR-UNAVAILABLE"
            )
            browser_context.grant_permissions(["clipboard-read", "clipboard-write"], origin="http://tauri.localhost")
            boundary.locator("[data-copy-diagnostic]").click()
            page.wait_for_function(
                "document.querySelector('[data-live-region]')?.textContent?.includes('Diagnostic reference copied')",
                timeout=5_000,
            )
            details["diagnosticCopy"] = page.evaluate("navigator.clipboard.readText()") == diagnostic
            boundary.locator("[data-retry-boundary]").click()
            page.wait_for_function(
                """() => document.querySelector('[data-local-service-boundary]')
                  ?.getAttribute('data-boundary-state') === 'recovery-required'
                  && document.querySelector('[data-live-region]')?.textContent
                    ?.includes('Local analytical service recovery-required')""",
                timeout=5_000,
            )
            details["boundaryRecovery"] = boundary.locator("[data-retry-boundary]").is_enabled()
            details["retainedInput"] = command.input_value() == "Retained local draft"
            open_desktop_tool(page, "Diagnostics & support")
            page.get_by_role("heading", name="Diagnostics unavailable").wait_for(state="visible", timeout=5_000)
            details["diagnosticsUnavailable"] = (
                page.locator("[data-diagnostics-workspace]").count() == 1
                and page.locator("h1").inner_text().strip() == "Diagnostics & support"
                and "No support data was exported" in page.locator("main").inner_text()
                and page.locator("[data-workflow-nav]").count() == 0
                and page.locator("[data-all-tools]").count() == 1
            )
            if page_errors:
                errors.append(f"desktop product runtime error: {'; '.join(page_errors)}")
            page.close()

            diagnostics = browser_context.new_page()
            diagnostics_errors: list[str] = []
            diagnostics.on("pageerror", page_error_collector(diagnostics_errors))
            diagnostics.add_init_script(
                r"""(() => {
                  const traceId = '0123456789abcdef0123456789abcdef';
                  const preview = {
                    previewId: 'a'.repeat(32),
                    outputDirectory: 'C:\\Research Observatory\\support-exports',
                    bundle: {
                      schemaVersion: '1.0',
                      documentType: 'research-observatory-support-bundle',
                      bundleId: 'c'.repeat(32),
                      generatedAtUnixMs: 1786534400000,
                      components: [
                        {componentId: 'desktop', version: '0.1.0', contractVersion: '1.0.0'},
                        {componentId: 'core-api', version: '0.1.0', contractVersion: '1.0.0'}
                      ],
                      runtime: {state: 'ready', attempt: 1, retryAvailable: false, diagnosticReference: null},
                      storage: [{storageId: 'application-data', status: 'available'}],
                      resources: {processRunning: true, workingSetBytes: 62230528},
                      recentDiagnostics: [{
                        sequence: 1,
                        code: 'RO-CORE-API-REQUEST-COMPLETE',
                        stream: 'api',
                        traceId
                      }],
                      exclusions: [
                        'project-documents', 'imported-sources', 'manuscript-content',
                        'search-and-query-text', 'credentials-and-tokens', 'environment-variables',
                        'raw-process-logs', 'process-identifiers', 'absolute-storage-paths'
                      ]
                    }
                  };
                  const completePreview = async () => {
                    const documentJson = `${JSON.stringify(preview.bundle, null, 2)}\n`;
                    const bytes = new TextEncoder().encode(documentJson);
                    const digest = await crypto.subtle.digest('SHA-256', bytes);
                    const sha256 = Array.from(new Uint8Array(digest), (byte) =>
                      byte.toString(16).padStart(2, '0')).join('');
                    return {...preview, documentJson, byteLength: bytes.byteLength, sha256};
                  };
                  window.__TAURI_INTERNALS__ = {
                    transformCallback: () => 1,
                    invoke: async (command, args) => {
                      if (command === 'application_lock_status') {
                        return {
                          schemaVersion: '1.0', state: 'unlocked', signInMode: 'none', policyRevision: 1,
                          profileName: null, inactivityTimeoutMinutes: 0,
                          configurationState: 'valid', reason: null,
                          threatDisclosure: 'Application-session protection only; '
                            + 'this is not Windows-account isolation.',
                          retryAfterSeconds: 0, auditSequence: 0
                        };
                      }
                      if (command === 'application_lock_activity' || command === 'plugin:event|unlisten') {
                        return undefined;
                      }
                      if (command === 'plugin:event|listen') return 1;
                      if (command === 'core_runtime_start' || command === 'core_runtime_status') {
                        return {state: 'ready', attempt: 1, retryAvailable: false, diagnosticReference: null};
                      }
                      if (command === 'core_runtime_stop') return undefined;
                      if (command === 'support_bundle_preview') return await completePreview();
                      if (command === 'support_bundle_export' && args?.previewId === preview.previewId) {
                        const completed = await completePreview();
                        return {
                          bundleId: preview.bundle.bundleId,
                          path: 'C:\\Research Observatory\\support-exports\\bundle.json',
                          byteLength: completed.byteLength,
                          sha256: completed.sha256
                        };
                      }
                      throw new Error('unsupported test command');
                    }
                  };
                })()"""
            )
            diagnostics.goto("http://tauri.localhost/index.html", wait_until="load")
            diagnostics.wait_for_function("document.body.dataset.applicationReady === 'true'", timeout=5_000)
            open_desktop_tool(diagnostics, "Diagnostics & support")
            diagnostics.wait_for_timeout(500)
            if diagnostics.get_by_role("heading", name="Exact support bundle preview").count() != 1:
                raise ValueError(
                    "functional diagnostics preview did not load: " + diagnostics.locator("main").inner_text()
                )
            diagnostics_text = diagnostics.locator("main").inner_text()
            exact_json = diagnostics.locator(".support-json-preview").text_content()
            details["diagnosticsPreview"] = (
                diagnostics.locator("h1").count() == 1
                and diagnostics.locator("h1").inner_text().strip() == "Diagnostics & support"
                and "Desktop" in diagnostics_text
                and "Core API" in diagnostics_text
                and "65,536" not in diagnostics_text
                and "credentials and tokens" in diagnostics_text
                and "private manuscript" not in diagnostics_text
                and exact_json is not None
                and '"bundleId": "cccccccccccccccccccccccccccccccc"' in exact_json
                and "support-exports" not in exact_json
                and exact_json.endswith("\n")
            )
            details["diagnosticsTraceLink"] = "0123456789abcdef0123456789abcdef" in diagnostics_text
            diagnostics.get_by_role("button", name="Export reviewed bundle").click()
            exported_status = diagnostics.locator(".support-preview [role='status']")
            exported_status.wait_for(state="visible", timeout=5_000)
            exported_button = diagnostics.locator(".support-preview button", has_text="Bundle exported")
            details["diagnosticsExactExport"] = (
                exported_button.count() == 1
                and exported_button.is_disabled()
                and "bundle.json" in exported_status.inner_text()
            )
            if diagnostics_errors:
                errors.append(f"desktop diagnostics runtime error: {'; '.join(diagnostics_errors)}")
            diagnostics.close()

            projects = browser_context.new_page()
            project_errors: list[str] = []
            projects.on("pageerror", page_error_collector(project_errors))
            projects.add_init_script(
                r"""(() => {
                  const traceId = '0123456789abcdef0123456789abcdef';
                  const projectId = '11111111-1111-4111-8111-111111111111';
                  let revision = 0;
                  let state = 'active';
                  let open = false;
                  let accessMode = 'closed';
                  let compatibilityState = 'compatible';
                  let packageFormatVersion = '1.0.0';
                  let backupRequiredBeforeRepair = false;
                  let recoveryAction = 'none';
                  window.__PROJECT_CALLS__ = [];
                  window.__PRIVACY_CALLS__ = [];
                  let privacyRevision = 0;
                  let networkPolicy = 'offline';
                  let telemetryMode = 'off';
                  const disclosure = {
                    disclosureVersion: 'secure-deletion-disclosure-v1',
                    scope: 'project-cache-only', logicalRemoval: true,
                    physicalErasureGuaranteed: false, canonicalProjectDataExcluded: true,
                    limitations: [
                      'Filesystem unlink does not prove physical media erasure.',
                      'SSD wear levelling and device remapping can retain prior blocks.',
                      'Filesystem journals, snapshots, backups, and hard links can retain copies.',
                      'Only the rebuildable project cache is cleared; canonical project data is excluded.'
                    ]
                  };
                  const workflowCatalog = __WORKFLOW_CATALOG__;
                  const currentIntent = {
                    schemaVersion: '1.0', intentId: '019d5f72-5331-7000-8000-000000000001',
                    revisionId: '019d5f72-5331-7000-8000-000000000002', revision: 1,
                    revisionContentHash: `sha256:${'a'.repeat(64)}`,
                    createdAt: '2026-09-03T12:00:00Z', status: 'draft',
                    primaryUseCase: 'theory-synthesis', epistemicMode: 'theory',
                    researchObjective: 'Explain a bounded evidence-first workflow.',
                    contributionIntent: 'Retain exact researcher authority.', phenomenon: 'Research workflow',
                    unitOfAnalysis: 'Project', levelOfAnalysis: 'System',
                    sourceKinds: ['peer-reviewed-article'], evidenceTypes: ['theoretical-work'],
                    languageCodes: ['en'], startYear: 2020, endYear: 2026,
                    includePrivateReports: false, noveltyStandard: 'theoretical',
                    noveltyRationale: 'Bound novelty against prior theory.', autonomyLevel: 'suggest',
                    stoppingConditions: ['interpretive-saturation'],
                    revisionRationale: 'Establish the bounded theory workflow.', unresolvedDecisions: [],
                    decisionComplete: true, canRequestAcceptance: true, launchReady: false
                  };
                  let workflowStageState = null;
                  let workflowSupportingHandoff = null;
                  const workflowProgress = () => ({
                    schemaVersion: '1.0', projectId,
                    selectionRevisionId: '019d5f72-5331-7000-8000-000000000031',
                    selectionRevisionContentHash: `sha256:${'7'.repeat(64)}`,
                    intentRevisionId: currentIntent.revisionId,
                    intentRevisionContentHash: currentIntent.revisionContentHash,
                    profileId: 'theory-synthesis', profileTitle: 'Theory synthesis',
                    processForm: 'linear', bootstrapRequired: workflowStageState === null,
                    current: workflowStageState,
                    recommendedStageKey: 'intent-contract-1',
                    recommendedPageContractId: 'intent-contract.html',
                    recommendedAction: workflowStageState === null
                      ? 'Start the guided workflow at this researcher-controlled stage.'
                      : 'Continue the current stage; completion requires explicit human evidence.',
                    checkpointState: 'unknown',
                    checkpointRationale:
                      'No stage-specific checkpoint authority is declared by the approved reference.',
                    supportingHandoff: workflowSupportingHandoff, staleOutputs: [], history: []
                  });
                  const privacyPolicy = () => ({
                    schemaVersion: '1.0', projectId, revision: privacyRevision,
                    defaultsApplied: privacyRevision === 0, networkPolicy,
                    remoteModelApproval: 'preview-every-task', telemetryMode,
                    logRetentionDays: 14, documentRetention: 'project-lifetime',
                    cacheRetentionDays: 30, egressConsentRecorded: networkPolicy !== 'offline',
                    egressEnforcement: networkPolicy === 'approved-providers'
                      ? 'require-task-preview' : 'deny', deletionDisclosure: disclosure
                  });
                  const projection = () => ({
                    schemaVersion: '1.0', projectId, displayName: 'Study One', templateId: 'theory-synthesis',
                    lifecycleState: state, root: 'C:/Research/study-one', open, accessMode,
                    compatibilityState, packageFormatVersion,
                    backupRequiredBeforeRepair, recoveryAction, revision,
                    deleteConfirmation: `delete:${projectId}`
                  });
                  window.__TAURI_INTERNALS__ = {
                    transformCallback: () => 1,
                    invoke: async (command, args) => {
                      if (command === 'application_lock_status') {
                        return {
                          schemaVersion: '1.0', state: 'unlocked', signInMode: 'none', policyRevision: 1,
                          profileName: null, inactivityTimeoutMinutes: 0,
                          configurationState: 'valid', reason: null,
                          threatDisclosure: 'Application-session protection only; '
                            + 'this is not Windows-account isolation.',
                          retryAfterSeconds: 0, auditSequence: 0
                        };
                      }
                      if (command === 'application_lock_activity' || command === 'plugin:event|unlisten') {
                        return undefined;
                      }
                      if (command === 'plugin:event|listen') return 1;
                      if (command === 'core_runtime_start' || command === 'core_runtime_status') {
                        return {state: 'ready', attempt: 1, retryAvailable: false, diagnosticReference: null};
                      }
                      if (command === 'core_runtime_stop') return undefined;
                      if (command !== 'core_api_request') throw new Error('unsupported test command');
                      const request = args?.request;
                      if (request?.path?.startsWith('/projects/privacy')) {
                        window.__PRIVACY_CALLS__.push(request);
                      } else {
                        window.__PROJECT_CALLS__.push(request);
                      }
                      if (request?.path === '/workflow-profiles/catalog') {
                        if (request.method !== 'GET' || request.body !== null || request.ifMatch !== null
                          || request.idempotencyKey !== null) throw new Error('invalid catalog request');
                        return {status: 200, contentType: 'application/json', traceId, etag: null,
                          body: JSON.stringify(workflowCatalog)};
                      }
                      const progressCommand = request?.path === '/projects/workflow-progress/commands';
                      if (request?.method !== 'POST' || request?.ifMatch !== null
                        || (progressCommand
                          ? !/^[0-9a-f]{32}$/.test(request?.idempotencyKey)
                          : request?.idempotencyKey !== null)) {
                        throw new Error('invalid project request envelope');
                      }
                      const body = JSON.parse(request.body);
                      let responseBody;
                      if (request.path === '/projects/workflow-progress') {
                        if (body.root !== 'C:/Research/study-one') throw new Error('invalid workflow progress root');
                        responseBody = workflowProgress();
                      } else if (request.path === '/projects/intent') {
                        if (body.root !== 'C:/Research/study-one') throw new Error('invalid intent root');
                        responseBody = {
                          schemaVersion: '1.0', projectId, current: currentIntent,
                          history: [{
                            revision: currentIntent.revision,
                            revisionId: currentIntent.revisionId,
                            revisionContentHash: currentIntent.revisionContentHash,
                            createdAt: currentIntent.createdAt,
                            status: currentIntent.status,
                            primaryUseCase: currentIntent.primaryUseCase,
                            unresolvedDecisionCount: currentIntent.unresolvedDecisions.length
                          }]
                        };
                      } else if (progressCommand) {
                        if (body.root !== 'C:/Research/study-one'
                          || body.stageKey !== 'intent-contract-1'
                          || body.expectedSelectionRevisionId !== '019d5f72-5331-7000-8000-000000000031'
                          || body.expectedSelectionRevisionContentHash !== `sha256:${'7'.repeat(64)}`
                          || body.revisitSourceStageStateRevisionId !== null
                          || body.revisitSourceStageStateRevisionContentHash !== null
                          || body.completionEvidenceRevisionIds.length !== 0
                          || body.rationale !== null) {
                          throw new Error('invalid workflow progress command');
                        }
                        if (body.action === 'start') {
                          if (body.expectedStageStateRevisionId !== null
                            || body.expectedStageStateRevisionContentHash !== null
                            || body.supportingPageContractId !== null || workflowStageState !== null) {
                            throw new Error('invalid workflow start command');
                          }
                          workflowStageState = {
                            stageStateId: '019d5f72-5331-7000-8000-000000000041',
                            stageStateRevisionId: '019d5f72-5331-7000-8000-000000000042',
                            revision: 1, revisionContentHash: `sha256:${'9'.repeat(64)}`,
                            parentStateRevisionId: null, stageKey: 'intent-contract-1',
                            pageContractId: 'intent-contract.html', navigationRole: 'primary',
                            passNumber: 1, status: 'current', completionEvidenceIds: [],
                            attentionReason: null, staleCauseIds: [], skipRationale: null,
                            updatedAt: '2026-09-04T02:00:00.000Z'
                          };
                        } else if (body.action === 'open-supporting') {
                          if (workflowStageState === null
                            || body.expectedStageStateRevisionId !== workflowStageState.stageStateRevisionId
                            || body.expectedStageStateRevisionContentHash !== workflowStageState.revisionContentHash
                            || !['index.html', 'project-settings.html', 'projects.html']
                              .includes(body.supportingPageContractId)) {
                            throw new Error('invalid supporting workflow command');
                          }
                          workflowSupportingHandoff = {
                            stageStateId: workflowStageState.stageStateId,
                            stageStateRevisionId: workflowStageState.stageStateRevisionId,
                            revisionContentHash: workflowStageState.revisionContentHash,
                            pageContractId: body.supportingPageContractId,
                            navigationRole: 'supporting',
                            returnStageStateRevisionId: workflowStageState.stageStateRevisionId
                          };
                        } else {
                          throw new Error('unexpected workflow action');
                        }
                        responseBody = workflowProgress();
                      } else if (request.path === '/projects/privacy') {
                        if (!open || accessMode !== 'read-write' || body.root !== 'C:/Research/study-one') {
                          throw new Error('privacy policy requested without writable project');
                        }
                        responseBody = privacyPolicy();
                      } else if (request.path === '/projects/privacy/update') {
                        if (body.root !== 'C:/Research/study-one' || body.expectedRevision !== privacyRevision
                          || body.remoteModelApproval !== 'preview-every-task'
                          || body.networkPolicy !== 'approved-providers'
                          || body.egressConsentToken !== 'acknowledge-egress-preview-v1') {
                          throw new Error('invalid privacy update');
                        }
                        privacyRevision += 1; networkPolicy = body.networkPolicy;
                        telemetryMode = body.telemetryMode; responseBody = privacyPolicy();
                      } else if (request.path === '/projects/privacy/cache/preview') {
                        if (body.root !== 'C:/Research/study-one') throw new Error('invalid cache preview');
                        const token = 'a'.repeat(32);
                        responseBody = {
                          schemaVersion: '1.0', projectId, policyRevision: privacyRevision,
                          previewToken: token, confirmation: `clear-cache:${token}`,
                          expiresAt: '2026-08-22T01:15:00Z', itemCount: 2, byteCount: 19,
                          deletionDisclosure: disclosure
                        };
                      } else if (request.path === '/projects/privacy/cache/clear') {
                        if (body.root !== 'C:/Research/study-one'
                          || body.previewToken !== 'a'.repeat(32)
                          || body.confirmation !== `clear-cache:${'a'.repeat(32)}`) {
                          throw new Error('invalid cache confirmation');
                        }
                        responseBody = {
                          schemaVersion: '1.0', projectId, state: 'cleared', itemCount: 2,
                          byteCount: 19, cleanupPending: false, deletionDisclosure: disclosure
                        };
                      } else if (request.path === '/projects') {
                        if (body.parentDirectory !== 'C:/Research' || body.directoryName !== 'study-one'
                          || body.displayName !== 'Study One' || body.primaryUseCase !== 'theory-synthesis'
                          || body.researchObjective !== 'Explain a bounded evidence-first workflow.') {
                          throw new Error('invalid create body');
                        }
                      } else if (request.path === '/projects/open') {
                        if (body.root === 'C:/Research/study-one') {
                          open = true; accessMode = 'read-write';
                        } else if (body.root === 'C:/Research/newer-study') {
                          state = 'active'; open = true; accessMode = 'read-only';
                          compatibilityState = 'newer-unsupported'; packageFormatVersion = '2.0.0';
                          backupRequiredBeforeRepair = true;
                          recoveryAction = 'backup-then-use-compatible-application';
                        } else if (body.root === 'C:/Research/newer-archived') {
                          state = 'archived'; open = false; accessMode = 'closed';
                          compatibilityState = 'newer-unsupported'; packageFormatVersion = '2.0.0';
                          backupRequiredBeforeRepair = true;
                          recoveryAction = 'backup-then-use-compatible-application';
                        } else throw new Error('invalid open root');
                      } else if (request.path === '/projects/close') {
                        open = false; accessMode = 'closed';
                      } else if (request.path === '/projects/archive') {
                        state = 'archived'; revision += 1;
                      } else if (request.path === '/projects/restore') {
                        state = 'active'; revision += 1;
                      } else if (request.path === '/projects/delete') {
                        if (body.confirmation !== `delete:${projectId}`) throw new Error('invalid confirmation');
                        state = 'trash'; revision += 1;
                      } else {
                        throw new Error('unsupported project path');
                      }
                      return {
                        status: 200, contentType: 'application/json', traceId, etag: null,
                        body: JSON.stringify(responseBody ?? projection())
                      };
                    }
                  };
                })()""".replace("__WORKFLOW_CATALOG__", workflow_catalog_json)
            )
            projects.goto("http://tauri.localhost/index.html", wait_until="load")
            projects.wait_for_function("document.body.dataset.applicationReady === 'true'", timeout=5_000)
            open_desktop_tool(projects, "Local projects")
            projects.locator("#project-parent-directory").fill("C:/Research")
            projects.locator("#project-directory-name").fill("study-one")
            projects.locator("#project-display-name").fill("Study One")
            projects.locator("#project-research-objective").fill("Explain a bounded evidence-first workflow.")
            implemented_tool_labels = [
                "Local projects",
                "Project home",
                "Research intent",
                "Task Center",
                "Audit & lineage",
                "Project settings",
                "Application settings",
                "Diagnostics & support",
            ]
            workflow_profile_rows = []
            for profile in workflow_catalog["profiles"]:
                projects.locator("#project-primary-use-case").select_option(profile["profileId"])
                preview = projects.locator(".workflow-profile-preview")
                rendered = preview.evaluate(
                    """element => ({
                      title: element.querySelector('h3')?.textContent?.trim() ?? '',
                      paragraphs: Array.from(element.querySelectorAll('p')).map(
                        (item) => item.textContent?.trim() ?? ''),
                      stages: Array.from(element.querySelectorAll('ol > li')).map(
                        (item) => item.textContent?.trim() ?? '')
                    })"""
                )
                all_tools = projects.locator("[data-all-tools]")
                tool_buttons = all_tools.locator("button")
                tool_labels = tool_buttons.evaluate_all(
                    "elements => elements.map((element) => element.getAttribute('aria-label'))"
                )
                expected_stages = [
                    f"{stage['label']}{' (optional)' if stage['optional'] else ''}"
                    for stage in profile["stages"]
                ]
                expected_paragraphs = [
                    profile["purpose"],
                    f"Expected output: {', '.join(profile['expectedOutputs'])}",
                    "Process form: "
                    + ("Revisitable process" if profile["processForm"] == "revisitable" else "Linear process"),
                    (
                        "All tools remain available. The selected workflow does not weaken evidence or provenance "
                        "requirements."
                    ),
                ]
                row = {
                    "profileId": profile["profileId"],
                    "processForm": profile["processForm"],
                    "title": rendered["title"] == profile["title"],
                    "guidance": rendered["paragraphs"] == expected_paragraphs,
                    "stageOrder": rendered["stages"] == expected_stages,
                    "allTools": tool_labels == implemented_tool_labels
                    and all(tool_buttons.nth(index).is_enabled() for index in range(len(implemented_tool_labels)))
                    and all_tools.locator("ul").get_attribute("aria-label") == "All implemented tools",
                }
                row["valid"] = all(
                    value is True for key, value in row.items() if key not in {"profileId", "processForm"}
                )
                workflow_profile_rows.append(row)
            details["workflowProfileMatrix"] = {
                "referenceId": workflow_catalog["referenceId"],
                "referenceVersion": workflow_catalog["referenceVersion"],
                "profileCatalogVersion": workflow_catalog["profileCatalogVersion"],
                "profileCatalogHash": workflow_catalog["profileCatalogHash"],
                "intentGuidanceHash": workflow_catalog["intentGuidanceHash"],
                "allToolsAccessible": workflow_catalog["allToolsAccessible"],
                "profiles": workflow_profile_rows,
            }
            details["workflowProfileMatrixValid"] = (
                workflow_catalog["referenceId"] == "RO-UI-ACADEMIC-MINIMAL-1.5"
                and workflow_catalog["referenceVersion"] == "1.5"
                and workflow_catalog["profileCatalogVersion"] == "1.0.0"
                and workflow_catalog["profileCatalogHash"]
                == "sha256:0a3887774b30bb2d2d7fced5c9e43452e7e34993407a6122155b740814350e49"
                and workflow_catalog["intentGuidanceHash"]
                == "sha256:2feffbaf216da3adb4d8fe0b3ca6e2579cdc2dcedc2d57341086a14def5fe0d2"
                and workflow_catalog["allToolsAccessible"] is True
                and len(workflow_profile_rows) == 14
                and all(row["valid"] for row in workflow_profile_rows)
                and {
                    row["profileId"] for row in workflow_profile_rows if row["processForm"] == "revisitable"
                }
                == {"hermeneutic-inquiry", "living-review", "manuscript-review-revision"}
            )
            projects.locator("#project-primary-use-case").select_option("theory-synthesis")
            workflow_preview_valid = (
                "Clarify and integrate constructs" in projects.locator("main").inner_text()
                and "Theory architecture, construct map" in projects.locator("main").inner_text()
                and "Linear process" in projects.locator("main").inner_text()
                and "Research Intent" in projects.locator("main").inner_text()
                and "Theory Map" in projects.locator("main").inner_text()
            )
            projects.get_by_role("button", name="Create project", exact=True).click()
            projects.locator("[data-current-project]").wait_for(state="visible", timeout=5_000)
            current = projects.locator("[data-current-project]")
            current.get_by_role("button", name="Open project", exact=True).click()
            current.get_by_text("Exclusive local session open", exact=True).wait_for(timeout=5_000)
            open_desktop_tool(projects, "Project home")
            projects.locator('[data-project-home-state="ready"]').wait_for(state="visible", timeout=5_000)
            project_home_bootstrap_valid = (
                "Theory synthesis · Linear workflow" in projects.locator("main").inner_text()
                and "Not started" in projects.locator("main").inner_text()
                and "Not yet governed" in projects.locator("main").inner_text()
                and "No stale or unknown-impact outputs are recorded" in projects.locator("main").inner_text()
            )
            projects.get_by_role("button", name="Start guided workflow", exact=True).click()
            projects.wait_for_function(
                "window.__PROJECT_CALLS__.some((request) => request.path === '/projects/workflow-progress/commands')",
                timeout=5_000,
            )
            open_desktop_tool(projects, "Project home")
            projects.get_by_role("button", name="Open current step", exact=True).wait_for(timeout=5_000)
            project_home_started_valid = (
                "intent-contract-1" in projects.locator("main").inner_text()
                and "Continue the current stage" in projects.locator("main").inner_text()
            )
            open_desktop_tool(projects, "Project settings")
            projects.locator("#privacy-network-policy").wait_for(state="visible", timeout=5_000)
            privacy_defaults_valid = (
                projects.locator("#privacy-network-policy").input_value() == "offline"
                and projects.locator("#usage-telemetry").input_value() == "off"
                and "Nothing. Offline is enforced" in projects.locator("[data-egress-preview]").inner_text()
                and "physical media erasure" in projects.locator("main").inner_text().casefold()
                and "canonical project data is excluded" in projects.locator("main").inner_text().casefold()
            )
            projects.locator("#privacy-network-policy").select_option("approved-providers")
            privacy_save = projects.get_by_role("button", name="Save project settings", exact=True)
            consent_required = privacy_save.is_disabled()
            projects.get_by_role("checkbox").check()
            privacy_save.click()
            projects.get_by_text("Policy revision 1", exact=True).wait_for(timeout=5_000)
            projects.get_by_role("button", name="Preview cache cleanup", exact=True).click()
            projects.locator("[data-cache-clear-preview]").wait_for(state="visible", timeout=5_000)
            projects.get_by_role("button", name="Confirm clear rebuildable cache", exact=True).click()
            projects.get_by_text("Cache cleanup result", exact=True).wait_for(timeout=5_000)
            details["privacySettingsWorkflow"] = (
                projects.evaluate(
                    r"""() => {
                  const calls = window.__PRIVACY_CALLS__;
                  const update = JSON.parse(calls[1].body);
                  return JSON.stringify(calls.map((request) => request.path)) === JSON.stringify([
                    '/projects/privacy', '/projects/privacy/update',
                    '/projects/privacy/cache/preview', '/projects/privacy/cache/clear'])
                    && update.egressConsentToken === 'acknowledge-egress-preview-v1'
                    && update.networkPolicy === 'approved-providers'
                    && update.telemetryMode === 'off'
                    && !calls.some((request) => request.body.includes('manuscript-content'))
                    && document.querySelector('main')?.textContent?.includes('Physical erasure is not guaranteed.');
                }"""
                )
                and privacy_defaults_valid
                and consent_required
            )
            open_desktop_tool(projects, "Local projects")
            current = projects.locator("[data-current-project]")
            current.get_by_text("Exclusive local session open", exact=True).wait_for(timeout=5_000)
            current.get_by_role("button", name="Close project", exact=True).click()
            current.get_by_text("Closed", exact=True).wait_for(timeout=5_000)
            current.get_by_role("button", name="Archive project", exact=True).click()
            current.get_by_role("button", name="Restore project", exact=True).wait_for(timeout=5_000)
            current.get_by_role("button", name="Restore project", exact=True).click()
            confirmation = "delete:11111111-1111-4111-8111-111111111111"
            current.locator("#project-delete-confirmation").fill(confirmation)
            current.get_by_role("button", name="Move to recoverable trash", exact=True).click()
            current.get_by_text("trash", exact=True).wait_for(timeout=5_000)
            projects.locator("#project-root").fill("C:/Research/newer-study")
            projects.get_by_role("button", name="Open project", exact=True).click()
            current.get_by_text("Read-only inspection open", exact=True).wait_for(timeout=5_000)
            current.get_by_text("Newer project format · read-only", exact=True).wait_for(timeout=5_000)
            safe_open_valid = projects.evaluate(
                """() => document.querySelector('[data-current-project]')?.textContent?.includes(
                    'First create and verify a complete backup')
                  && !Array.from(document.querySelectorAll('[data-current-project] button')).some(
                    (button) => ['Archive project','Move to recoverable trash'].includes(
                      button.textContent?.trim() ?? ''))"""
            )
            current.get_by_role("button", name="Close project", exact=True).click()
            current.get_by_text("Closed", exact=True).wait_for(timeout=5_000)
            projects.locator("#project-root").fill("C:/Research/newer-archived")
            projects.get_by_role("button", name="Open project", exact=True).click()
            current.get_by_text("archived", exact=True).wait_for(timeout=5_000)
            archived_incompatible_valid = projects.evaluate(
                """() => document.querySelector('[data-current-project]')?.textContent?.includes(
                    'First create and verify a complete backup')
                  && !Array.from(document.querySelectorAll('[data-current-project] button')).some(
                    (button) => ['Restore project','Archive project','Move to recoverable trash'].includes(
                      button.textContent?.trim() ?? ''))"""
            )
            project_sequence_valid = projects.evaluate(
                """() => JSON.stringify(window.__PROJECT_CALLS__.map((request) => request.path))
                  === JSON.stringify(['/workflow-profiles/catalog','/projects','/projects/open',
                    '/workflow-profiles/catalog','/projects/intent','/projects/workflow-progress',
                    '/projects/workflow-progress/commands','/projects/workflow-progress/commands',
                    '/projects/workflow-progress/commands','/projects/workflow-progress/commands',
                    '/workflow-profiles/catalog',
                    '/projects/close','/projects/archive',
                    '/projects/restore','/projects/delete','/projects/open','/projects/close','/projects/open'])
                  && document.querySelector('[data-current-project]')?.textContent?.includes('Revision 3')
                  && document.querySelectorAll('[data-all-tools]').length === 1
                  && !document.querySelector('[data-workflow-select], [data-workflow-nav]')"""
            )
            projects.keyboard.press("Control+K")
            projects.wait_for_function("document.activeElement?.id === 'shell-command'", timeout=5_000)
            details["projectsWorkflowCases"] = {
                "safeOpen": safe_open_valid,
                "archivedIncompatible": archived_incompatible_valid,
                "projectSequence": project_sequence_valid,
                "workflowPreview": workflow_preview_valid,
                "projectHomeBootstrap": project_home_bootstrap_valid,
                "projectHomeStarted": project_home_started_valid,
                "requestPaths": projects.evaluate("() => window.__PROJECT_CALLS__.map((request) => request.path)"),
            }
            details["projectsWorkflow"] = (
                safe_open_valid
                and archived_incompatible_valid
                and project_sequence_valid
                and workflow_preview_valid
                and project_home_bootstrap_valid
                and project_home_started_valid
                and projects.evaluate("document.activeElement?.id === 'shell-command'")
            )
            if project_errors:
                errors.append(f"desktop projects runtime error: {'; '.join(project_errors)}")
            projects.close()

            revisit = browser_context.new_page()
            revisit_errors: list[str] = []
            revisit.on("pageerror", page_error_collector(revisit_errors))
            revisit.add_init_script(
                r"""(() => {
                  const catalog = __WORKFLOW_CATALOG__;
                  const profile = catalog.profiles.find(
                    (candidate) => candidate.profileId === 'hermeneutic-inquiry');
                  const project = {
                    schemaVersion: '1.0', projectId: '33333333-3333-4333-8333-333333333333',
                    displayName: 'Revisitable Study', templateId: 'hermeneutic-inquiry',
                    lifecycleState: 'active', root: 'C:/Research/revisitable-study', open: true,
                    accessMode: 'read-write', compatibilityState: 'compatible',
                    packageFormatVersion: '1.0.0', backupRequiredBeforeRepair: false,
                    recoveryAction: 'none', revision: 0,
                    deleteConfirmation: 'delete:33333333-3333-4333-8333-333333333333'
                  };
                  const intent = {
                    schemaVersion: '1.0', intentId: '019d5f72-5331-7000-8000-000000000101',
                    revisionId: '019d5f72-5331-7000-8000-000000000102', revision: 1,
                    revisionContentHash: `sha256:${'1'.repeat(64)}`,
                    createdAt: '2026-09-04T03:00:00Z', status: 'draft',
                    primaryUseCase: 'hermeneutic-inquiry', epistemicMode: 'hermeneutic',
                    researchObjective: 'Revisit an earlier interpretive stage without losing later work.',
                    contributionIntent: 'Preserve each interpretive pass.', phenomenon: 'Research workflow',
                    unitOfAnalysis: 'Project', levelOfAnalysis: 'System',
                    sourceKinds: ['peer-reviewed-article'], evidenceTypes: ['interpretive-text'],
                    languageCodes: ['en'], startYear: 2020, endYear: 2026,
                    includePrivateReports: false, noveltyStandard: 'interpretive',
                    noveltyRationale: 'Bound claims to the current reading.', autonomyLevel: 'suggest',
                    stoppingConditions: ['interpretive-saturation'],
                    revisionRationale: 'Exercise an explicit earlier-stage pass.', unresolvedDecisions: [],
                    decisionComplete: true, canRequestAcceptance: true, launchReady: false
                  };
                  const source = {
                    stageStateId: '019d5f72-5331-7000-8000-000000000111',
                    stageStateRevisionId: '019d5f72-5331-7000-8000-000000000112', revision: 2,
                    revisionContentHash: `sha256:${'2'.repeat(64)}`, parentStateRevisionId: null,
                    stageKey: profile.stages[0].stageKey, pageContractId: profile.stages[0].pageContractId,
                    navigationRole: 'primary', passNumber: 1, status: 'completed',
                    completionEvidenceIds: ['019d5f72-5331-7000-8000-000000000141'], attentionReason: null,
                    staleCauseIds: [], skipRationale: null, updatedAt: '2026-09-04T03:01:00.000Z'
                  };
                  const active = {
                    stageStateId: '019d5f72-5331-7000-8000-000000000121',
                    stageStateRevisionId: '019d5f72-5331-7000-8000-000000000122', revision: 1,
                    revisionContentHash: `sha256:${'4'.repeat(64)}`, parentStateRevisionId: null,
                    stageKey: profile.stages[1].stageKey, pageContractId: profile.stages[1].pageContractId,
                    navigationRole: 'primary', passNumber: 1, status: 'current',
                    completionEvidenceIds: [], attentionReason: null, staleCauseIds: [],
                    skipRationale: null, updatedAt: '2026-09-04T03:02:00.000Z'
                  };
                  let progress = {
                    schemaVersion: '1.0', projectId: project.projectId,
                    selectionRevisionId: '019d5f72-5331-7000-8000-000000000131',
                    selectionRevisionContentHash: `sha256:${'5'.repeat(64)}`,
                    intentRevisionId: intent.revisionId,
                    intentRevisionContentHash: intent.revisionContentHash,
                    profileId: profile.profileId, profileTitle: profile.title,
                    processForm: profile.processForm, bootstrapRequired: false, current: active,
                    recommendedStageKey: active.stageKey,
                    recommendedPageContractId: active.pageContractId,
                    recommendedAction: 'Continue the current stage; completion requires explicit human evidence.',
                    checkpointState: profile.stages[1].checkpointState,
                    checkpointRationale: profile.stages[1].checkpointRationale,
                    supportingHandoff: null, staleOutputs: [], history: [source]
                  };
                  window.__REVISIT_REQUEST__ = null;
                  window.__REVISIT_PROGRESS__ = null;
                  const coreResponse = (body) => ({status: 200, contentType: 'application/json',
                    traceId: '0123456789abcdef0123456789abcdef', etag: null,
                    body: JSON.stringify(body)});
                  window.__TAURI_INTERNALS__ = {
                    transformCallback: () => 1,
                    invoke: async (command, args) => {
                      if (command === 'application_lock_status') return {
                        schemaVersion: '1.0', state: 'unlocked', signInMode: 'none', policyRevision: 1,
                        profileName: null, inactivityTimeoutMinutes: 0, configurationState: 'valid',
                        reason: null, threatDisclosure: 'Application-session protection only; '
                          + 'this is not Windows-account isolation.', retryAfterSeconds: 0, auditSequence: 0
                      };
                      if (command === 'application_lock_activity' || command === 'plugin:event|unlisten') {
                        return undefined;
                      }
                      if (command === 'plugin:event|listen') return 1;
                      if (command === 'core_runtime_start' || command === 'core_runtime_status') {
                        return {state: 'ready', attempt: 1, retryAvailable: false, diagnosticReference: null};
                      }
                      if (command === 'core_runtime_stop') return undefined;
                      if (command !== 'core_api_request') throw new Error(`unexpected command: ${command}`);
                      const request = args?.request;
                      if (request.path === '/workflow-profiles/catalog') return coreResponse(catalog);
                      const body = JSON.parse(request.body);
                      if (request.path === '/projects') return coreResponse(project);
                      if (request.path === '/projects/intent') return coreResponse({
                        schemaVersion: '1.0', projectId: project.projectId, current: intent,
                        history: [{revision: 1, revisionId: intent.revisionId,
                          revisionContentHash: intent.revisionContentHash, createdAt: intent.createdAt,
                          status: intent.status, primaryUseCase: intent.primaryUseCase,
                          unresolvedDecisionCount: 0}]
                      });
                      if (request.path === '/projects/workflow-progress') return coreResponse(progress);
                      if (request.path !== '/projects/workflow-progress/commands'
                        || !/^[0-9a-f]{32}$/.test(request.idempotencyKey)
                        || body.root !== project.root || body.action !== 'revisit'
                        || body.stageKey !== source.stageKey
                        || body.expectedSelectionRevisionId !== progress.selectionRevisionId
                        || body.expectedSelectionRevisionContentHash !== progress.selectionRevisionContentHash
                        || body.expectedStageStateRevisionId !== active.stageStateRevisionId
                        || body.expectedStageStateRevisionContentHash !== active.revisionContentHash
                        || body.revisitSourceStageStateRevisionId !== source.stageStateRevisionId
                        || body.revisitSourceStageStateRevisionContentHash !== source.revisionContentHash
                        || body.completionEvidenceRevisionIds.length !== 0
                        || body.supportingPageContractId !== null || body.rationale !== null) {
                        throw new Error('invalid selected-source revisit request');
                      }
                      window.__REVISIT_REQUEST__ = body;
                      const displaced = {...active,
                        stageStateRevisionId: '019d5f72-5331-7000-8000-000000000123', revision: 2,
                        revisionContentHash: `sha256:${'6'.repeat(64)}`,
                        parentStateRevisionId: active.stageStateRevisionId, status: 'in-progress',
                        updatedAt: '2026-09-04T03:03:00.000Z'};
                      const revisited = {...source,
                        stageStateRevisionId: '019d5f72-5331-7000-8000-000000000113', revision: 3,
                        revisionContentHash: `sha256:${'7'.repeat(64)}`,
                        parentStateRevisionId: source.stageStateRevisionId, passNumber: 2,
                        status: 'current', completionEvidenceIds: [],
                        updatedAt: '2026-09-04T03:03:00.000Z'};
                      progress = {...progress, current: revisited,
                        recommendedStageKey: revisited.stageKey,
                        recommendedPageContractId: revisited.pageContractId,
                        history: [displaced, active, source]};
                      window.__REVISIT_PROGRESS__ = progress;
                      return coreResponse(progress);
                    }
                  };
                })()""".replace("__WORKFLOW_CATALOG__", workflow_catalog_json)
            )
            revisit.goto("http://tauri.localhost/index.html", wait_until="load")
            revisit.wait_for_function("document.body.dataset.applicationReady === 'true'", timeout=5_000)
            open_desktop_tool(revisit, "Local projects")
            revisit.locator("#project-parent-directory").fill("C:/Research")
            revisit.locator("#project-directory-name").fill("revisitable-study")
            revisit.locator("#project-display-name").fill("Revisitable Study")
            revisit.locator("#project-research-objective").fill(
                "Revisit an earlier interpretive stage without losing later work."
            )
            revisit.locator("#project-primary-use-case").select_option("hermeneutic-inquiry")
            revisit.get_by_role("button", name="Create project", exact=True).click()
            try:
                revisit.locator("[data-workflow-nav]").wait_for(timeout=5_000)
            except PlaywrightError:
                details["workflowEarlierStageRevisitDiagnostics"] = revisit.evaluate(
                    "() => ({body: document.body.innerText, project: "
                    "document.querySelector('[data-current-project]')?.textContent ?? null})"
                )
                raise
            open_desktop_tool(revisit, "Project home")
            revisit_button = revisit.get_by_role("button", name="Revisit intent-contract-1", exact=True)
            revisit_button.wait_for(timeout=5_000)
            ordinary_navigation_preserved = (
                revisit.locator('[data-workflow-stage-key="intent-contract-1"] > button').count() == 1
            )
            revisit_button.click()
            revisit.wait_for_function("window.__REVISIT_REQUEST__ !== null", timeout=5_000)
            open_desktop_tool(revisit, "Project home")
            details["workflowEarlierStageRevisit"] = (
                revisit.evaluate(
                    """() => {
                  const request = window.__REVISIT_REQUEST__;
                  const result = window.__REVISIT_PROGRESS__;
                  return request?.stageKey === 'intent-contract-1'
                    && request?.expectedStageStateRevisionId
                      === '019d5f72-5331-7000-8000-000000000122'
                    && request?.revisitSourceStageStateRevisionId
                      === '019d5f72-5331-7000-8000-000000000112'
                    && result?.current?.stageKey === 'intent-contract-1'
                    && result?.current?.passNumber === 2
                    && result?.history?.some((stage) => stage.stageKey !== 'intent-contract-1'
                      && stage.status === 'in-progress')
                    && result?.history?.some((stage) => stage.stageKey === 'intent-contract-1'
                      && stage.status === 'completed' && stage.passNumber === 1)
                    && document.querySelector('[data-workflow-nav] [data-stage-state=current]')
                      ?.getAttribute('data-workflow-stage-key') === 'intent-contract-1'
                    && Array.from(document.querySelectorAll('[data-workflow-nav] [data-stage-state=in-progress]'))
                      .some((node) => node.getAttribute('data-workflow-stage-key') !== 'intent-contract-1');
                }"""
                )
                and ordinary_navigation_preserved
            )
            if revisit_errors:
                errors.append(f"desktop earlier-stage revisit runtime error: {'; '.join(revisit_errors)}")
            revisit.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
            revisit.close()

            event_acl_startup_cases: dict[str, bool] = {}
            for listener_mode in ("allowed", "denied", "timed-out"):
                startup = browser_context.new_page()
                startup_errors: list[str] = []
                startup.on("pageerror", page_error_collector(startup_errors))
                startup.add_init_script(
                    r"""(() => {
                      const listenerMode = '__LISTENER_MODE__';
                      const calls = [];
                      window.__LOCK_STARTUP_CALLS__ = calls;
                      const unlocked = {
                        schemaVersion: '1.0', state: 'unlocked', signInMode: 'none', policyRevision: 1,
                        profileName: null, inactivityTimeoutMinutes: 0, configurationState: 'valid',
                        reason: null, threatDisclosure: 'Application-session protection only; '
                          + 'this is not Windows-account isolation.', retryAfterSeconds: 0, auditSequence: 0
                      };
                      window.__TAURI_INTERNALS__ = {
                        transformCallback: () => 1,
                        invoke: async (command) => {
                          if (command === 'plugin:event|listen') {
                            calls.push(command);
                            if (listenerMode === 'denied') throw new Error('event listen denied');
                            if (listenerMode === 'timed-out') return await new Promise(() => {});
                            return 1;
                          }
                          if (command === 'application_lock_status') {
                            calls.push(command);
                            return {...unlocked};
                          }
                          if (command === 'application_lock_activity'
                            || command === 'plugin:event|unlisten') return undefined;
                          if (command === 'core_runtime_start' || command === 'core_runtime_status') {
                            return {state: 'ready', attempt: 1, retryAvailable: false,
                              diagnosticReference: null};
                          }
                          if (command === 'core_runtime_stop') return undefined;
                          throw new Error(`unsupported event ACL startup command: ${command}`);
                        }
                      };
                    })()""".replace("__LISTENER_MODE__", listener_mode)
                )
                startup.goto("http://tauri.localhost/index.html", wait_until="load")
                startup.wait_for_function(
                    "window.__LOCK_STARTUP_CALLS__.includes('application_lock_status')",
                    timeout=5_000,
                )
                if listener_mode == "allowed":
                    startup.wait_for_function("document.body.dataset.applicationReady === 'true'", timeout=5_000)
                    observed_startup = startup.evaluate(
                        """() => ({
                          calls: window.__LOCK_STARTUP_CALLS__,
                          locked: document.querySelector('[data-application-locked]') !== null,
                          recovery: document.querySelector('[data-application-locked]')
                            ?.textContent.includes('Recovery required') ?? false
                        })"""
                    )
                    event_acl_startup_cases["defaultNoLogin"] = (
                        observed_startup["calls"][:2] == ["plugin:event|listen", "application_lock_status"]
                        and not observed_startup["locked"]
                        and not observed_startup["recovery"]
                    )
                    if not event_acl_startup_cases["defaultNoLogin"]:
                        details["applicationLockEventAclStartupDiagnostics"] = observed_startup
                else:
                    startup.locator("[data-application-locked]").wait_for(timeout=5_000)
                    case_name = "deniedListener" if listener_mode == "denied" else "timedOutListener"
                    event_acl_startup_cases[case_name] = startup.evaluate(
                        """() => window.__LOCK_STARTUP_CALLS__[0] === 'plugin:event|listen'
                          && window.__LOCK_STARTUP_CALLS__.includes('application_lock_status')
                          && document.querySelector('[data-application-locked]')
                            ?.textContent.includes('Recovery required')
                          && document.querySelector('#shell-command, nav, footer') === null"""
                    )
                if startup_errors:
                    errors.append(f"desktop {listener_mode} event-listener startup error: {'; '.join(startup_errors)}")
                startup.close()

            locked = browser_context.new_page()
            locked_errors: list[str] = []
            locked.on("pageerror", page_error_collector(locked_errors))
            locked.add_init_script(
                r"""(() => {
                  window.__TAURI_INTERNALS__ = {
                    transformCallback: () => 1,
                    invoke: async (command) => {
                      if (command === 'application_lock_status') {
                        return {
                          schemaVersion: '1.0', state: 'locked', signInMode: 'windows-password',
                          policyRevision: 1, profileName: null, inactivityTimeoutMinutes: 15,
                          configurationState: 'valid', reason: 'application-restart',
                          threatDisclosure: 'Application-session protection only; '
                            + 'this is not Windows-account isolation.',
                          retryAfterSeconds: 0, auditSequence: 4
                        };
                      }
                      if (command === 'plugin:event|listen') return 1;
                      if (command === 'plugin:event|unlisten') return undefined;
                      throw new Error('protected command reached while locked');
                    }
                  };
                })()"""
            )
            locked.goto("http://tauri.localhost/index.html", wait_until="load")
            locked.locator("[data-application-locked]").wait_for(state="visible", timeout=5_000)
            locked_text = locked.locator("body").inner_text()
            details["applicationLock"] = (
                locked.locator("h1").count() == 1
                and locked.locator("h1").inner_text().strip() == "Research Observatory is locked"
                and locked.get_by_role("button", name="Unlock with Windows password", exact=True).count() == 1
                and "not Windows-account isolation" in locked_text
                and "No Research Observatory or cloud account is required" in locked_text
                and locked.locator(
                    "#shell-command, [data-local-service-boundary], [data-current-project], nav, footer"
                ).count()
                == 0
            )
            if locked_errors:
                errors.append(f"desktop locked runtime error: {'; '.join(locked_errors)}")
            locked.close()

            lock_reconciliation = browser_context.new_page()
            reconciliation_errors: list[str] = []
            lock_reconciliation.on("pageerror", page_error_collector(reconciliation_errors))
            lock_reconciliation.add_init_script(
                r"""(() => {
                  const callbacks = new Map();
                  let nextCallback = 1;
                  let lockListener = null;
                  let failStatus = false;
                  let transitionConflict = false;
                  let transitionCommitAttempts = 0;
                  let delayNextDraft = false;
                  let delayNextAcceptance = false;
                  let releaseDelayedDraft = null;
                  let releaseDelayedAcceptance = null;
                  let snapshot = {
                    schemaVersion: '1.0', state: 'unlocked', signInMode: 'windows-password',
                    policyRevision: 1, profileName: 'Private profile', inactivityTimeoutMinutes: 15,
                    configurationState: 'valid', reason: null,
                    threatDisclosure: 'Application-session protection only; '
                      + 'this is not Windows-account isolation.',
                    retryAfterSeconds: 0, auditSequence: 1
                  };
                  const workflowCatalog = __WORKFLOW_CATALOG__;
                  const projection = {
                    schemaVersion: '1.0', projectId: '11111111-1111-4111-8111-111111111111',
                    displayName: 'Sensitive Study', templateId: 'theory-synthesis',
                    lifecycleState: 'active', root: 'C:/Private/sensitive-study', open: true,
                    accessMode: 'read-write', compatibilityState: 'compatible',
                    packageFormatVersion: '1.0.0', backupRequiredBeforeRepair: false,
                    recoveryAction: 'none', revision: 0,
                    deleteConfirmation: 'delete:11111111-1111-4111-8111-111111111111'
                  };
                  let currentIntent = {
                    schemaVersion: '1.0', intentId: '019d5f72-5331-7000-8000-000000000001',
                    revisionId: '019d5f72-5331-7000-8000-000000000002', revision: 1,
                    revisionContentHash: `sha256:${'a'.repeat(64)}`, createdAt: '2026-09-03T12:00:00Z',
                    status: 'draft', primaryUseCase: 'theory-synthesis', epistemicMode: 'theory',
                    researchObjective: 'Preserve a bounded sensitive workflow.',
                    contributionIntent: 'Retain exact researcher authority.', phenomenon: 'Research workflow',
                    unitOfAnalysis: 'Project', levelOfAnalysis: 'System',
                    sourceKinds: ['peer-reviewed-article'], evidenceTypes: ['theoretical-work'],
                    languageCodes: ['en'], startYear: 2020, endYear: 2026, includePrivateReports: false,
                    noveltyStandard: 'theoretical', noveltyRationale: 'Bound novelty against prior theory.',
                    autonomyLevel: 'suggest', stoppingConditions: ['interpretive-saturation'],
                    revisionRationale: 'Establish the bounded theory workflow.', unresolvedDecisions: [],
                    decisionComplete: true, canRequestAcceptance: true, launchReady: false
                  };
                  const projectionB = {
                    ...projection,
                    projectId: '22222222-2222-4222-8222-222222222222',
                    displayName: 'Second Study', root: 'C:/Private/study-two',
                    deleteConfirmation: 'delete:22222222-2222-4222-8222-222222222222'
                  };
                  let currentIntentB = {
                    ...currentIntent,
                    intentId: '019d5f72-5331-7000-8000-000000000021',
                    revisionId: '019d5f72-5331-7000-8000-000000000022',
                    revisionContentHash: `sha256:${'2'.repeat(64)}`,
                    researchObjective: 'Keep project B authoritative during delayed project A responses.'
                  };
                  let workflowSupportingHandoff = null;
                  const currentWorkflowStage = (selectedProjection, profile) => {
                    const firstProject = selectedProjection.projectId.startsWith('1111');
                    return {
                      stageStateId: firstProject
                        ? '019d5f72-5331-7000-8000-000000000061'
                        : '019d5f72-5331-7000-8000-000000000071',
                      stageStateRevisionId: firstProject
                        ? '019d5f72-5331-7000-8000-000000000062'
                        : '019d5f72-5331-7000-8000-000000000072',
                      revision: 1,
                      revisionContentHash: `sha256:${(firstProject ? '4' : '5').repeat(64)}`,
                      parentStateRevisionId: null, stageKey: profile.stages[0].stageKey,
                      pageContractId: profile.stages[0].pageContractId, navigationRole: 'primary',
                      passNumber: 1, status: 'current', completionEvidenceIds: [], attentionReason: null,
                      staleCauseIds: [], skipRationale: null, updatedAt: '2026-09-04T03:00:00.000Z'
                    };
                  };
                  const workflowProgress = (selectedProjection, selectedIntent) => {
                    const profile = workflowCatalog.profiles.find(
                      (candidate) => candidate.profileId === selectedIntent.primaryUseCase);
                    const current = currentWorkflowStage(selectedProjection, profile);
                    return {
                      schemaVersion: '1.0', projectId: selectedProjection.projectId,
                      selectionRevisionId: selectedProjection.projectId.startsWith('1111')
                        ? '019d5f72-5331-7000-8000-000000000031'
                        : '019d5f72-5331-7000-8000-000000000032',
                      selectionRevisionContentHash: `sha256:${(
                        selectedProjection.projectId.startsWith('1111') ? '7' : '8').repeat(64)}`,
                      intentRevisionId: selectedIntent.revisionId,
                      intentRevisionContentHash: selectedIntent.revisionContentHash,
                      profileId: profile.profileId, profileTitle: profile.title,
                      processForm: profile.processForm, bootstrapRequired: false, current,
                      recommendedStageKey: profile.stages[0].stageKey,
                      recommendedPageContractId: profile.stages[0].pageContractId,
                      recommendedAction: 'Start the guided workflow at this researcher-controlled stage.',
                      checkpointState: profile.stages[0].checkpointState,
                      checkpointRationale: profile.stages[0].checkpointRationale,
                      supportingHandoff: selectedProjection.projectId.startsWith('1111')
                        ? workflowSupportingHandoff : null,
                      staleOutputs: [], history: []
                    };
                  };
                  const coreResponse = (body) => ({status: 200, contentType: 'application/json',
                    traceId: '0123456789abcdef0123456789abcdef', etag: null,
                    body: JSON.stringify(body)});
                  window.__EXPECTED_CATALOG__ = workflowCatalog;
                  window.__DELAY_NEXT_DRAFT__ = () => { delayNextDraft = true; };
                  window.__DELAY_NEXT_ACCEPTANCE__ = () => { delayNextAcceptance = true; };
                  window.__RELEASE_DELAYED_DRAFT__ = () => {
                    const release = releaseDelayedDraft;
                    releaseDelayedDraft = null;
                    if (release) release();
                  };
                  window.__RELEASE_DELAYED_ACCEPTANCE__ = () => {
                    const release = releaseDelayedAcceptance;
                    releaseDelayedAcceptance = null;
                    if (release) release();
                  };
                  window.__LOCK_EMIT__ = (payload) => {
                    const callback = callbacks.get(lockListener);
                    if (callback) callback({event: 'application-lock-changed', id: lockListener, payload});
                  };
                  window.__LOCK_SET_STATUS__ = (next) => { snapshot = next; };
                  window.__LOCK_FAIL_STATUS__ = () => { failStatus = true; };
                  window.__LOCK_ENABLE_TRANSITION_CONFLICT__ = () => {
                    transitionConflict = true;
                    transitionCommitAttempts = 0;
                  };
                  window.__TAURI_INTERNALS__ = {
                    transformCallback: (callback, once = false) => {
                      const id = nextCallback++;
                      callbacks.set(id, (value) => {
                        if (once) callbacks.delete(id);
                        return callback(value);
                      });
                      return id;
                    },
                    unregisterCallback: (id) => callbacks.delete(id),
                    invoke: async (command, args) => {
                      if (command === 'plugin:event|listen') {
                        lockListener = args.handler;
                        return args.handler;
                      }
                      if (command === 'plugin:event|unlisten') {
                        callbacks.delete(args.id);
                        return undefined;
                      }
                      if (command === 'application_lock_status') {
                        if (failStatus) throw new Error('monitor unavailable');
                        return {...snapshot};
                      }
                      if (command === 'application_sign_in_transition_prepare' && transitionConflict) {
                        return {schemaVersion: '1.0', outcome: 'prepared',
                          reasonCode: 'RO-SIGN-IN-TRANSITION-PREPARED', handle: 'ab'.repeat(32),
                          sourceMode: snapshot.signInMode, targetMode: args.targetMode,
                          warningRequired: false, snapshot: {...snapshot}};
                      }
                      if (command === 'application_sign_in_transition_commit' && transitionConflict) {
                        if (args?.confirmed === false) {
                          return {schemaVersion: '1.0', outcome: 'cancelled',
                            reasonCode: 'RO-SIGN-IN-TRANSITION-CONFIRMATION-CANCELLED', handle: null,
                            sourceMode: 'windows-password', targetMode: 'windows-password',
                            warningRequired: false, snapshot: {...snapshot}};
                        }
                        transitionCommitAttempts += 1;
                        if (transitionCommitAttempts === 2) {
                          snapshot = {...snapshot, profileName: 'Other profile',
                            inactivityTimeoutMinutes: 0, policyRevision: snapshot.policyRevision + 1,
                            auditSequence: snapshot.auditSequence + 1};
                        }
                        throw new Error('simulated transition response loss');
                      }
                      if (command === 'application_lock_activity') return undefined;
                      if (command === 'application_lock_unlock') {
                        failStatus = false;
                        snapshot = {...snapshot, state: 'unlocked', profileName: 'Private profile',
                          reason: null, auditSequence: snapshot.auditSequence + 1};
                        return {schemaVersion: '1.0', outcome: 'succeeded',
                          reasonCode: 'RO-LOCK-UNLOCKED', snapshot: {...snapshot}};
                      }
                      if (command === 'core_runtime_start' || command === 'core_runtime_status') {
                        return {state: 'ready', attempt: 1, retryAvailable: false, diagnosticReference: null};
                      }
                      if (command === 'core_runtime_stop') return undefined;
                      if (command === 'core_api_request'
                        && args?.request?.path === '/workflow-profiles/catalog') {
                        return {status: 200, contentType: 'application/json',
                          traceId: '0123456789abcdef0123456789abcdef', etag: null,
                          body: JSON.stringify(workflowCatalog)};
                      }
                      if (command === 'core_api_request' && args?.request?.path === '/projects') {
                        const body = JSON.parse(args.request.body);
                        if (body.primaryUseCase !== 'theory-synthesis'
                          || body.researchObjective !== 'Preserve a bounded sensitive workflow.') {
                          throw new Error('invalid governed project creation');
                        }
                        return {status: 200, contentType: 'application/json',
                          traceId: '0123456789abcdef0123456789abcdef', etag: null,
                          body: JSON.stringify(projection)};
                      }
                      if (command === 'core_api_request' && args?.request?.path === '/projects/open') {
                        const body = JSON.parse(args.request.body);
                        if (body.root === projection.root) return coreResponse(projection);
                        if (body.root === projectionB.root) return coreResponse(projectionB);
                        throw new Error('unknown project root');
                      }
                      if (command === 'core_api_request' && args?.request?.path === '/projects/intent') {
                        const body = JSON.parse(args.request.body);
                        const selectedProjection = body.root === projectionB.root ? projectionB : projection;
                        const selectedIntent = body.root === projectionB.root ? currentIntentB : currentIntent;
                        return coreResponse({schemaVersion: '1.0',
                          projectId: selectedProjection.projectId, current: selectedIntent,
                          history: [{revision: selectedIntent.revision,
                            revisionId: selectedIntent.revisionId,
                            revisionContentHash: selectedIntent.revisionContentHash,
                            createdAt: selectedIntent.createdAt, status: selectedIntent.status,
                          primaryUseCase: selectedIntent.primaryUseCase, unresolvedDecisionCount: 0}]});
                      }
                      if (command === 'core_api_request'
                        && args?.request?.path === '/projects/workflow-progress') {
                        const body = JSON.parse(args.request.body);
                        const selectedProjection = body.root === projectionB.root ? projectionB : projection;
                        const selectedIntent = body.root === projectionB.root ? currentIntentB : currentIntent;
                        return coreResponse(workflowProgress(selectedProjection, selectedIntent));
                      }
                      if (command === 'core_api_request'
                        && args?.request?.path === '/projects/workflow-progress/commands') {
                        const body = JSON.parse(args.request.body);
                        const selectedProgress = workflowProgress(projection, currentIntent);
                        const current = selectedProgress.current;
                        if (body.root !== projection.root || body.action !== 'open-supporting'
                          || body.stageKey !== current.stageKey
                          || body.expectedSelectionRevisionId !== selectedProgress.selectionRevisionId
                          || body.expectedSelectionRevisionContentHash
                            !== selectedProgress.selectionRevisionContentHash
                          || body.expectedStageStateRevisionId !== current.stageStateRevisionId
                          || body.expectedStageStateRevisionContentHash !== current.revisionContentHash
                          || body.revisitSourceStageStateRevisionId !== null
                          || body.revisitSourceStageStateRevisionContentHash !== null
                          || body.completionEvidenceRevisionIds.length !== 0
                          || body.supportingPageContractId !== 'index.html' || body.rationale !== null) {
                          throw new Error('invalid server-issued supporting handoff request');
                        }
                        workflowSupportingHandoff = {
                          stageStateId: current.stageStateId,
                          stageStateRevisionId: current.stageStateRevisionId,
                          revisionContentHash: current.revisionContentHash,
                          pageContractId: body.supportingPageContractId,
                          navigationRole: 'supporting',
                          returnStageStateRevisionId: current.stageStateRevisionId
                        };
                        return coreResponse(workflowProgress(projection, currentIntent));
                      }
                      if (command === 'core_api_request'
                        && args?.request?.path === '/projects/intent/preview') {
                        const body = JSON.parse(args.request.body);
                        if (body.expectedRevision !== 1 || body.primaryUseCase !== 'systematic-review'
                          || JSON.stringify(body.stoppingConditions) !== JSON.stringify(['coverage-threshold'])) {
                          throw new Error('invalid governed stopping preview request');
                        }
                        return {status: 200, contentType: 'application/json',
                          traceId: '0123456789abcdef0123456789abcdef', etag: null,
                          body: JSON.stringify({schemaVersion: '1.0', expectedRevision: 1,
                            changeCategories: ['primary-use-case'], affectedWorkflows: ['Research Intent'],
                            affectedOutputs: ['Protocol, corpus, evidence table, cited synthesis, and audit bundle'],
                            affectedSchemas: ['research-intent-revision', 'project-workflow-selection',
                              'workflow-profile-migration'], affectedCheckpoints: ['Theory Map'],
                            autonomyDefaultEffects: ['retained autonomy level: suggest'],
                            stoppingLogicEffects: ['removed stopping condition: interpretive-saturation',
                              'added stopping condition: coverage-threshold'], staleArtifactIds: [],
                            allToolsAccessible: true, evidenceRequirementsUnchanged: true,
                            provenanceRequirementsUnchanged: true,
                            warnings: ['Ordered workflow, validation checkpoints, and expected outputs will change.'],
                            acknowledgementRequired: true, acknowledgementToken: 'b'.repeat(64)})};
                      }
                      if (command === 'core_api_request'
                        && args?.request?.path === '/projects/intent/drafts') {
                        const body = JSON.parse(args.request.body);
                        if (body.root !== projection.root || !args.request.idempotencyKey
                          || body.expectedRevision !== currentIntent.revision
                          || (body.expectedRevision === 1
                            && (body.primaryUseCase !== 'systematic-review'
                              || body.impactAcknowledgement !== 'b'.repeat(64)))) {
                          throw new Error('invalid governed intent save request');
                        }
                        const nextRevision = body.expectedRevision + 1;
                        currentIntent = {
                          ...currentIntent,
                          revisionId: nextRevision === 2
                            ? '019d5f72-5331-7000-8000-000000000003'
                            : '019d5f72-5331-7000-8000-000000000005',
                          revision: nextRevision,
                          revisionContentHash: `sha256:${(nextRevision === 2 ? 'c' : 'e').repeat(64)}`,
                          createdAt: '2026-09-03T12:05:00Z',
                          status: 'draft', primaryUseCase: body.primaryUseCase,
                          epistemicMode: 'systematic', researchObjective: body.researchObjective,
                          contributionIntent: body.contributionIntent, phenomenon: body.phenomenon,
                          unitOfAnalysis: body.unitOfAnalysis, levelOfAnalysis: body.levelOfAnalysis,
                          sourceKinds: body.sourceKinds, evidenceTypes: body.evidenceTypes,
                          languageCodes: body.languageCodes, startYear: body.startYear,
                          endYear: body.endYear, includePrivateReports: body.includePrivateReports,
                          noveltyStandard: body.noveltyStandard,
                          noveltyRationale: body.noveltyRationale,
                          autonomyLevel: body.autonomyLevel,
                          stoppingConditions: body.stoppingConditions,
                          revisionRationale: body.revisionRationale,
                          unresolvedDecisions: [], decisionComplete: true,
                          canRequestAcceptance: true, launchReady: false
                        };
                        const result = coreResponse(currentIntent);
                        if (delayNextDraft) {
                          delayNextDraft = false;
                          return new Promise((resolve) => { releaseDelayedDraft = () => resolve(result); });
                        }
                        return result;
                      }
                      if (command === 'core_api_request'
                        && args?.request?.path === '/projects/intent/acceptances') {
                        const body = JSON.parse(args.request.body);
                        if (body.root !== projection.root || !args.request.idempotencyKey
                          || body.expectedRevision !== currentIntent.revision
                          || body.expectedRevisionContentHash !== currentIntent.revisionContentHash
                          || body.confirmed !== true) {
                          throw new Error('invalid governed intent acceptance request');
                        }
                        currentIntent = {
                          ...currentIntent,
                          revisionId: '019d5f72-5331-7000-8000-000000000006',
                          revision: currentIntent.revision + 1,
                          revisionContentHash: `sha256:${'f'.repeat(64)}`,
                          createdAt: '2026-09-03T12:10:00Z', status: 'accepted',
                          canRequestAcceptance: false, launchReady: true
                        };
                        const result = coreResponse(currentIntent);
                        if (delayNextAcceptance) {
                          delayNextAcceptance = false;
                          return new Promise((resolve) => { releaseDelayedAcceptance = () => resolve(result); });
                        }
                        return result;
                      }
                      throw new Error(`unsupported lock reconciliation command: ${command}`);
                    }
                  };
                })()""".replace("__WORKFLOW_CATALOG__", workflow_catalog_json)
            )
            lock_reconciliation.goto("http://tauri.localhost/index.html", wait_until="load")
            lock_reconciliation.wait_for_function("document.body.dataset.applicationReady === 'true'", timeout=5_000)
            open_desktop_tool(lock_reconciliation, "Local projects")
            lock_reconciliation.locator("#project-parent-directory").fill("C:/Private")
            lock_reconciliation.locator("#project-directory-name").fill("sensitive-study")
            lock_reconciliation.locator("#project-display-name").fill("Sensitive Study")
            lock_reconciliation.locator("#project-research-objective").fill("Preserve a bounded sensitive workflow.")
            lock_reconciliation.locator("#project-primary-use-case").select_option("theory-synthesis")
            lock_reconciliation.get_by_role("button", name="Create project", exact=True).click()
            lock_reconciliation.locator("[data-current-project]").wait_for(timeout=5_000)
            lock_reconciliation.locator("[data-workflow-nav]").wait_for(timeout=5_000)
            initial_adaptive_navigation = lock_reconciliation.evaluate(
                """() => {
                  const profile = window.__EXPECTED_CATALOG__.profiles.find(
                    (candidate) => candidate.profileId === 'theory-synthesis');
                  const actual = Array.from(document.querySelectorAll('[data-workflow-stage-key]'))
                    .map((node) => node.getAttribute('data-workflow-stage-key'));
                  const context = document.querySelector('[data-workflow-context]')?.textContent ?? '';
                  return JSON.stringify(actual) === JSON.stringify(profile.stages.map((stage) => stage.stageKey))
                    && document.querySelectorAll('[data-workflow-nav] [aria-current=step]').length === 1
                    && document.querySelector('[data-workflow-nav] [data-stage-state=current]')
                      ?.getAttribute('data-workflow-stage-key') === profile.stages[0].stageKey
                    && context.includes(profile.stages[0].rationale)
                    && profile.expectedOutputs.every((output) => context.includes(output))
                    && context.includes('Quality gate · Unknown')
                    && document.querySelectorAll('[data-all-tools] li').length === 8
                    && !document.querySelector('a[href$=".html"]');
                }"""
            )
            open_desktop_tool(lock_reconciliation, "Research intent")
            try:
                lock_reconciliation.locator("#intent-use-case").wait_for(timeout=5_000)
            except PlaywrightError:
                details["applicationSettingsPositionDiagnostics"] = lock_reconciliation.evaluate(
                    "() => ({body: document.body.innerText, workspace: "
                    "document.querySelector('[data-intent-workspace]') !== null})"
                )
                raise
            lock_reconciliation.locator("#intent-use-case").select_option("systematic-review")
            systematic_default_applied = (
                lock_reconciliation.get_by_role("checkbox", name="coverage-threshold", exact=True).is_checked()
                and not lock_reconciliation.get_by_role(
                    "checkbox", name="interpretive-saturation", exact=True
                ).is_checked()
            )
            lock_reconciliation.get_by_role("button", name="Preview revision effects", exact=True).click()
            lock_reconciliation.get_by_text(
                "removed stopping condition: interpretive-saturation", exact=False
            ).wait_for(timeout=5_000)
            stopping_effects_rendered = (
                "removed stopping condition: interpretive-saturation"
                in lock_reconciliation.locator("[data-intent-workspace]").inner_text()
                and "added stopping condition: coverage-threshold"
                in lock_reconciliation.locator("[data-intent-workspace]").inner_text()
            )
            unsaved_profile_retained = lock_reconciliation.evaluate(
                """() => {
                  const expected = window.__EXPECTED_CATALOG__.profiles.find(
                    (candidate) => candidate.profileId === 'theory-synthesis').stages.map(
                      (stage) => stage.stageKey);
                  const actual = Array.from(document.querySelectorAll('[data-workflow-stage-key]'))
                    .map((node) => node.getAttribute('data-workflow-stage-key'));
                  return JSON.stringify(actual) === JSON.stringify(expected);
                }"""
            )
            lock_reconciliation.locator(".intent-impact input[type=checkbox]").check()
            lock_reconciliation.locator("#intent-rationale").fill("Persist the reviewed systematic workflow.")
            lock_reconciliation.get_by_role("button", name="Save draft revision", exact=True).click()
            lock_reconciliation.wait_for_function(
                """() => {
                  const expected = window.__EXPECTED_CATALOG__.profiles.find(
                    (candidate) => candidate.profileId === 'systematic-review').stages.map(
                      (stage) => stage.stageKey);
                  const actual = Array.from(document.querySelectorAll('[data-workflow-stage-key]'))
                    .map((node) => node.getAttribute('data-workflow-stage-key'));
                  return JSON.stringify(actual) === JSON.stringify(expected)
                    && document.querySelector('[data-workflow-nav] [data-stage-state=current]')
                      ?.getAttribute('data-workflow-stage-key') === expected[0];
                }""",
                timeout=5_000,
            )
            persisted_profile_applied = (
                "Revision 2" in lock_reconciliation.locator("[data-intent-workspace]").inner_text()
            )
            lock_reconciliation.locator("#intent-objective").fill("Unsaved workflow position")
            topbar_settings = lock_reconciliation.get_by_role("button", name="Private profile", exact=True)
            topbar_settings.click()
            lock_reconciliation.locator("[data-application-settings]").wait_for(timeout=5_000)
            lock_reconciliation.get_by_role("button", name="Return", exact=True).click()
            lock_reconciliation.wait_for_function(
                "document.activeElement?.textContent?.trim() === 'Private profile'", timeout=5_000
            )
            workflow_round_trip = (
                lock_reconciliation.locator("#intent-use-case").input_value() == "systematic-review"
                and lock_reconciliation.locator("#intent-objective").input_value() == "Unsaved workflow position"
                and "Sensitive Study" in lock_reconciliation.locator("[data-project-context]").inner_text()
            )
            sidebar_settings = lock_reconciliation.locator('nav button[aria-label="Application settings"]')
            sidebar_settings.click(timeout=5_000)
            lock_reconciliation.get_by_role("button", name="Return", exact=True).click()
            lock_reconciliation.wait_for_function(
                "document.activeElement?.getAttribute('aria-label') === 'Application settings'", timeout=5_000
            )
            sidebar_focus = sidebar_settings.evaluate("element => document.activeElement === element")
            open_desktop_tool(lock_reconciliation, "Project home")
            lock_reconciliation.locator("[data-supporting-tool]").wait_for(timeout=5_000)
            support_return = lock_reconciliation.get_by_role(
                "button", name="Return to current step · Research Intent", exact=True
            )
            supporting_return_valid = (
                support_return.count() == 1
                and "Supporting tool · Project home"
                in lock_reconciliation.locator("[data-supporting-tool]").inner_text()
            )
            support_return.click()
            lock_reconciliation.locator("#intent-use-case").wait_for(timeout=5_000)
            supporting_return_valid = supporting_return_valid and lock_reconciliation.evaluate(
                """() => document.querySelector('[data-supporting-tool]') === null
                  && document.querySelector('[data-workflow-nav] [data-stage-state=current]')
                    ?.getAttribute('data-workflow-stage-key') === 'intent-contract-1'"""
            )
            lock_reconciliation.locator("#intent-objective").fill("Delayed project A draft response")
            lock_reconciliation.locator("#intent-rationale").fill("Exercise the project-bound response guard.")
            lock_reconciliation.evaluate("window.__DELAY_NEXT_DRAFT__()")
            lock_reconciliation.get_by_role("button", name="Save draft revision", exact=True).click()
            lock_reconciliation.get_by_role("button", name="Saving locally…", exact=True).wait_for(timeout=5_000)
            open_desktop_tool(lock_reconciliation, "Local projects")
            lock_reconciliation.locator("#project-root").fill("C:/Private/study-two")
            lock_reconciliation.get_by_role("button", name="Open project", exact=True).click()
            lock_reconciliation.locator('[data-current-project="22222222-2222-4222-8222-222222222222"]').wait_for(
                timeout=5_000
            )
            lock_reconciliation.locator("[data-workflow-nav]").wait_for(timeout=5_000)
            lock_reconciliation.evaluate("window.__RELEASE_DELAYED_DRAFT__()")
            lock_reconciliation.wait_for_timeout(100)
            delayed_draft_guarded = lock_reconciliation.evaluate(
                """() => {
                  const expected = window.__EXPECTED_CATALOG__.profiles.find(
                    (candidate) => candidate.profileId === 'theory-synthesis').stages.map(
                      (stage) => stage.stageKey);
                  const actual = Array.from(document.querySelectorAll('[data-workflow-stage-key]'))
                    .map((node) => node.getAttribute('data-workflow-stage-key'));
                  return document.querySelector('[data-current-project]')
                      ?.getAttribute('data-current-project') === '22222222-2222-4222-8222-222222222222'
                    && JSON.stringify(actual) === JSON.stringify(expected)
                    && (document.querySelector('[data-project-context]')?.textContent ?? '')
                      .includes('Second Study');
                }"""
            )
            lock_reconciliation.locator("#project-root").fill("C:/Private/sensitive-study")
            lock_reconciliation.get_by_role("button", name="Open project", exact=True).click()
            lock_reconciliation.locator('[data-current-project="11111111-1111-4111-8111-111111111111"]').wait_for(
                timeout=5_000
            )
            open_desktop_tool(lock_reconciliation, "Research intent")
            lock_reconciliation.locator("#intent-acceptance-rationale").wait_for(timeout=5_000)
            lock_reconciliation.locator(".ro-status-badge").filter(has_text="Revision 3").wait_for(timeout=5_000)
            lock_reconciliation.locator("#intent-acceptance-rationale").fill(
                "Accept the exact persisted project A revision."
            )
            lock_reconciliation.locator(".intent-acceptance input[type=checkbox]").check()
            lock_reconciliation.evaluate("window.__DELAY_NEXT_ACCEPTANCE__()")
            lock_reconciliation.get_by_role("button", name="Accept intent revision", exact=True).click()
            lock_reconciliation.get_by_text("Acceptance request in progress", exact=False).wait_for(timeout=5_000)
            open_desktop_tool(lock_reconciliation, "Local projects")
            lock_reconciliation.locator("#project-root").fill("C:/Private/study-two")
            lock_reconciliation.get_by_role("button", name="Open project", exact=True).click()
            lock_reconciliation.locator('[data-current-project="22222222-2222-4222-8222-222222222222"]').wait_for(
                timeout=5_000
            )
            lock_reconciliation.locator("[data-workflow-nav]").wait_for(timeout=5_000)
            lock_reconciliation.evaluate("window.__RELEASE_DELAYED_ACCEPTANCE__()")
            lock_reconciliation.wait_for_timeout(100)
            delayed_acceptance_guarded = lock_reconciliation.evaluate(
                """() => document.querySelector('[data-current-project]')
                    ?.getAttribute('data-current-project') === '22222222-2222-4222-8222-222222222222'
                  && (document.querySelector('[data-project-context]')?.textContent ?? '')
                    .includes('Second Study')
                  && document.querySelector('[data-workflow-nav] [data-stage-state=current]')
                    ?.getAttribute('data-workflow-stage-key') === 'intent-contract-1'"""
            )
            details["adaptiveWorkflowNavigation"] = (
                initial_adaptive_navigation
                and unsaved_profile_retained
                and persisted_profile_applied
                and supporting_return_valid
            )
            details["intentMutationRaceGuarded"] = delayed_draft_guarded and delayed_acceptance_guarded
            lock_reconciliation.keyboard.press("Control+K")
            lock_reconciliation.locator("#shell-command").fill("application settings")
            command_settings = lock_reconciliation.get_by_role("button", name="Open application settings", exact=True)
            command_settings.click()
            lock_reconciliation.get_by_role("button", name="Return", exact=True).click()
            try:
                lock_reconciliation.wait_for_function(
                    "document.activeElement?.getAttribute('data-command-id') === 'open-application-settings'",
                    timeout=5_000,
                )
            except PlaywrightError:
                details["applicationSettingsFocusDiagnostics"] = lock_reconciliation.evaluate(
                    "() => ({active: document.activeElement?.outerHTML, commandConnected: "
                    "document.querySelector('[data-command-id=open-application-settings]')?.isConnected})"
                )
                raise
            command_focus = command_settings.evaluate("element => document.activeElement === element")
            details["applicationSettingsPositionPreserved"] = workflow_round_trip
            details["intentStoppingEffects"] = systematic_default_applied and stopping_effects_rendered
            details["applicationSettingsFocusRestoration"] = sidebar_focus and command_focus
            lock_reconciliation.locator("#shell-command").fill("private query")
            lock_reconciliation.get_by_role("button", name="Private profile", exact=True).click()
            lock_reconciliation.locator("#application-profile-name").fill("Private profile draft")
            lock_reconciliation.wait_for_timeout(1_200)
            details["applicationSettingsDraftReconciliation"] = (
                lock_reconciliation.locator("#application-profile-name").input_value() == "Private profile draft"
            )
            lock_reconciliation.evaluate("window.__LOCK_ENABLE_TRANSITION_CONFLICT__()")
            lock_reconciliation.locator("#application-profile-name").fill("Requested")
            lock_reconciliation.locator("#application-lock-timeout").select_option("60")
            lock_reconciliation.get_by_role("button", name="Save change", exact=True).click()
            conflict_message = (
                "The native policy changed elsewhere, so the requested sign-in change was not confirmed. "
                "Review the current setting before retrying."
            )
            lock_reconciliation.locator(".settings-feedback-danger").filter(has_text=conflict_message).wait_for(
                timeout=5_000
            )
            lock_reconciliation.wait_for_function(
                "message => document.querySelector('[data-live-region]')?.textContent === message",
                arg=conflict_message,
                timeout=5_000,
            )
            details["applicationSettingsConflictAnnouncement"] = (
                lock_reconciliation.locator(".settings-feedback-danger").inner_text() == conflict_message
                and lock_reconciliation.locator("#application-profile-name").input_value() == "Other profile"
                and lock_reconciliation.locator("#application-lock-timeout").input_value() == "0"
                and "prior setting remains active" not in lock_reconciliation.locator("[data-live-region]").inner_text()
            )
            lock_reconciliation.evaluate(
                """(() => {
                  const restored = {
                    schemaVersion: '1.0', state: 'unlocked', signInMode: 'windows-password',
                    policyRevision: 3, profileName: 'Private profile', inactivityTimeoutMinutes: 15,
                    configurationState: 'valid', reason: null,
                    threatDisclosure: 'Application-session protection only; this is not Windows-account isolation.',
                    retryAfterSeconds: 0, auditSequence: 3
                  };
                  window.__LOCK_SET_STATUS__(restored);
                  window.__LOCK_EMIT__(restored);
                })()"""
            )
            lock_reconciliation.wait_for_function("document.querySelector('#application-lock-timeout')?.value === '15'")
            lock_reconciliation.evaluate(
                """window.__LOCK_SET_STATUS__({
                  schemaVersion: '1.0', state: 'locked', signInMode: 'windows-password',
                  policyRevision: 3, profileName: null, inactivityTimeoutMinutes: 15,
                  configurationState: 'valid', reason: 'manual',
                  threatDisclosure: 'Application-session protection only; this is not Windows-account isolation.',
                  retryAfterSeconds: 0, auditSequence: 4
                })"""
            )
            lock_reconciliation.evaluate("window.__LOCK_EMIT__({malformed: true})")
            lock_reconciliation.locator("[data-application-locked]").wait_for(timeout=5_000)
            malformed_text = lock_reconciliation.locator("body").inner_text()
            malformed_locked = (
                "Sensitive Study" not in malformed_text
                and "C:/Private" not in malformed_text
                and "private query" not in malformed_text
                and "Private profile draft" not in malformed_text
                and lock_reconciliation.locator(
                    "#shell-command, [data-current-project], #application-profile-name, nav, footer"
                ).count()
                == 0
            )
            lock_reconciliation.get_by_role("button", name="Unlock with Windows password", exact=True).click()
            lock_reconciliation.locator(".application-shell[data-application-ready]").wait_for(timeout=5_000)
            normal_unlock = (
                "No project open" in lock_reconciliation.locator("body").inner_text()
                and lock_reconciliation.locator("#shell-command").input_value() == ""
                and lock_reconciliation.locator("[data-current-project], #application-profile-name").count() == 0
            )
            lock_reconciliation.evaluate(
                """window.__LOCK_SET_STATUS__({
                  schemaVersion: '1.0', state: 'locked', signInMode: 'windows-password',
                  policyRevision: 3, profileName: null, inactivityTimeoutMinutes: 15,
                  configurationState: 'valid', reason: 'inactivity',
                  threatDisclosure: 'Application-session protection only; this is not Windows-account isolation.',
                  retryAfterSeconds: 0, auditSequence: 6
                })"""
            )
            lock_reconciliation.locator("[data-application-locked]").wait_for(timeout=4_000)
            missed_event_locked = lock_reconciliation.locator("#shell-command, nav, footer").count() == 0
            lock_reconciliation.get_by_role("button", name="Unlock with Windows password", exact=True).click()
            lock_reconciliation.locator(".application-shell[data-application-ready]").wait_for(timeout=5_000)
            lock_reconciliation.evaluate("window.__LOCK_FAIL_STATUS__()")
            lock_reconciliation.locator("[data-application-locked]").wait_for(timeout=4_000)
            monitor_failure_locked = (
                "Application-lock status is unavailable" in lock_reconciliation.locator("body").inner_text()
                and lock_reconciliation.locator("#shell-command, nav, footer").count() == 0
            )
            details["applicationLockReconciliationCases"] = {
                "malformedEvent": malformed_locked,
                "normalUnlock": normal_unlock,
                "missedEvent": missed_event_locked,
                "monitorFailure": monitor_failure_locked,
            }
            details["applicationLockReconciliation"] = (
                malformed_locked and normal_unlock and missed_event_locked and monitor_failure_locked
            )
            event_acl_startup_cases["malformedEvent"] = malformed_locked
            details["applicationLockEventAclStartupCases"] = event_acl_startup_cases
            details["applicationLockEventAclStartup"] = all(event_acl_startup_cases.values())
            if reconciliation_errors:
                errors.append(f"desktop lock reconciliation runtime error: {'; '.join(reconciliation_errors)}")
            lock_reconciliation.close()

            lock_race = browser_context.new_page()
            race_errors: list[str] = []
            lock_race.on("pageerror", page_error_collector(race_errors))
            lock_race.add_init_script(
                r"""(() => {
                  const callbacks = new Map();
                  let nextCallback = 1;
                  let listener = null;
                  let resolveStatus;
                  const staleStatus = new Promise((resolve) => { resolveStatus = resolve; });
                  const unlocked = {
                    schemaVersion: '1.0', state: 'unlocked', signInMode: 'windows-password',
                    policyRevision: 1, profileName: null, inactivityTimeoutMinutes: 15,
                    configurationState: 'valid', reason: null,
                    threatDisclosure: 'Application-session protection only; '
                      + 'this is not Windows-account isolation.',
                    retryAfterSeconds: 0, auditSequence: 3
                  };
                  window.__LOCK_RACE_READY__ = false;
                  window.__LOCK_RACE__ = () => {
                    callbacks.get(listener)?.({event: 'application-lock-changed', id: listener,
                      payload: {...unlocked, state: 'locked', reason: 'manual', auditSequence: 4}});
                    resolveStatus({...unlocked});
                  };
                  window.__TAURI_INTERNALS__ = {
                    transformCallback: (callback) => {
                      const id = nextCallback++;
                      callbacks.set(id, callback);
                      return id;
                    },
                    unregisterCallback: (id) => callbacks.delete(id),
                    invoke: async (command, args) => {
                      if (command === 'plugin:event|listen') {
                        listener = args.handler;
                        window.__LOCK_RACE_READY__ = true;
                        return args.handler;
                      }
                      if (command === 'plugin:event|unlisten') return undefined;
                      if (command === 'application_lock_status') return await staleStatus;
                      throw new Error(`unsupported lock race command: ${command}`);
                    }
                  };
                })()"""
            )
            lock_race.goto("http://tauri.localhost/index.html", wait_until="load")
            lock_race.wait_for_function("window.__LOCK_RACE_READY__ === true", timeout=5_000)
            lock_race.evaluate("window.__LOCK_RACE__()")
            lock_race.locator("[data-application-locked]").wait_for(timeout=5_000)
            lock_race.wait_for_timeout(100)
            stale_status_denied = lock_race.locator("[data-application-locked]").count() == 1
            details["applicationLockReconciliation"] = details["applicationLockReconciliation"] and stale_status_denied
            if race_errors:
                errors.append(f"desktop lock race runtime error: {'; '.join(race_errors)}")
            lock_race.close()

            hello_recovery = browser_context.new_page()
            hello_recovery_errors: list[str] = []
            hello_recovery.on("pageerror", page_error_collector(hello_recovery_errors))
            hello_recovery.add_init_script(
                r"""(() => {
                  const callbacks = new Map();
                  let nextCallback = 1;
                  let listener = null;
                  let resolveCommit;
                  let snapshot = {
                    schemaVersion: '1.0', state: 'locked', signInMode: 'windows-hello',
                    policyRevision: 1, profileName: null, inactivityTimeoutMinutes: 15,
                    configurationState: 'valid', reason: 'application-restart',
                    threatDisclosure: 'Application-session protection only; '
                      + 'this is not Windows-account isolation.',
                    retryAfterSeconds: 0, auditSequence: 4
                  };
                  const prepared = () => ({
                    schemaVersion: '1.0', outcome: 'prepared',
                    reasonCode: 'RO-SIGN-IN-RECOVERY-PREPARED', handle: 'ab'.repeat(32),
                    sourceMode: 'windows-hello', targetMode: 'none', warningRequired: true,
                    snapshot: {...snapshot}
                  });
                  const transition = (outcome, reasonCode, nextSnapshot) => ({
                    schemaVersion: '1.0', outcome, reasonCode, handle: null,
                    sourceMode: 'windows-hello', targetMode: 'none', warningRequired: true,
                    snapshot: {...nextSnapshot}
                  });
                  window.__HELLO_COMMIT_CALLS__ = [];
                  window.__HELLO_RESOLVE_COMMIT__ = () => {
                    snapshot = {...snapshot, state: 'unlocked', signInMode: 'none',
                      policyRevision: 2, profileName: null, inactivityTimeoutMinutes: 0,
                      configurationState: 'valid', reason: null, auditSequence: 6};
                    resolveCommit?.(transition(
                      'committed', 'RO-SIGN-IN-RECOVERY-COMMITTED', snapshot
                    ));
                  };
                  window.__TAURI_INTERNALS__ = {
                    transformCallback: (callback, once = false) => {
                      const id = nextCallback++;
                      callbacks.set(id, (value) => {
                        if (once) callbacks.delete(id);
                        return callback(value);
                      });
                      return id;
                    },
                    unregisterCallback: (id) => callbacks.delete(id),
                    invoke: async (command, args) => {
                      if (command === 'plugin:event|listen') {
                        listener = args.handler;
                        return args.handler;
                      }
                      if (command === 'plugin:event|unlisten') {
                        callbacks.delete(args.id);
                        return undefined;
                      }
                      if (command === 'application_lock_status') return {...snapshot};
                      if (command === 'application_lock_hello_availability') {
                        return {schemaVersion: '1.0', provider: 'windows-hello',
                          availability: 'not-configured'};
                      }
                      if (command === 'application_sign_in_password_recovery_prepare') {
                        return prepared();
                      }
                      if (command === 'application_sign_in_transition_commit') {
                        window.__HELLO_COMMIT_CALLS__.push(args.confirmed);
                        if (!args.confirmed) {
                          return transition(
                            'cancelled', 'RO-SIGN-IN-TRANSITION-CONFIRMATION-CANCELLED', snapshot
                          );
                        }
                        return await new Promise((resolve) => { resolveCommit = resolve; });
                      }
                      if (command === 'application_lock_activity') return undefined;
                      if (command === 'core_runtime_start' || command === 'core_runtime_status') {
                        return {state: 'ready', attempt: 1, retryAvailable: false,
                          diagnosticReference: null};
                      }
                      if (command === 'core_runtime_stop') return undefined;
                      throw new Error(`unsupported Hello recovery command: ${command}`);
                    }
                  };
                })()"""
            )
            hello_recovery.goto("http://tauri.localhost/index.html", wait_until="load")
            hello_recovery.locator("[data-application-locked]").wait_for(timeout=5_000)
            hello_recovery.get_by_text(
                "Set up Windows Hello in Windows before selecting it here", exact=False
            ).wait_for(timeout=5_000)
            retry_visible = (
                hello_recovery.get_by_role("button", name="Unlock with Windows Hello", exact=True).count() == 1
            )
            recovery = hello_recovery.get_by_role("button", name="Use Windows password recovery", exact=True)
            recovery.click()
            dialog = hello_recovery.get_by_role("alertdialog")
            dialog.wait_for(timeout=5_000)
            hello_recovery.get_by_role("button", name="Keep application locked", exact=True).wait_for(
                state="visible", timeout=5_000
            )
            hello_recovery.wait_for_function(
                "!Array.from(document.querySelectorAll('button')).find((button) => "
                "button.textContent?.trim() === 'Keep application locked')?.disabled",
                timeout=5_000,
            )
            hello_recovery.wait_for_function(
                "document.activeElement?.textContent?.trim() === 'Keep application locked'",
                timeout=5_000,
            )
            modal_focus = hello_recovery.evaluate(
                "document.activeElement?.textContent?.trim() === 'Keep application locked'"
            )
            modal_background_inert = hello_recovery.evaluate(
                "document.querySelector('.locked-surface-content')?.inert === true "
                "&& document.querySelector('.locked-surface-content')?.getAttribute('aria-hidden') === 'true'"
            )
            global_shortcuts_suppressed = True
            for shortcut in ("Control+K", "Control+/", "Alt+H"):
                hello_recovery.keyboard.press(shortcut)
                global_shortcuts_suppressed = global_shortcuts_suppressed and hello_recovery.evaluate(
                    "document.querySelector('[role=alertdialog]')?.contains(document.activeElement) === true"
                )
            hello_recovery.keyboard.press("Escape")
            hello_recovery.wait_for_timeout(250)
            escaped = dialog.count() == 0
            if not escaped:
                details["applicationHelloRecoveryEscapeDiagnostics"] = hello_recovery.evaluate(
                    "() => ({body: document.body.innerText, active: document.activeElement?.textContent?.trim(), "
                    "calls: window.__HELLO_COMMIT_CALLS__})"
                )
                hello_recovery.get_by_role("button", name="Keep application locked", exact=True).click()
                dialog.wait_for(state="detached", timeout=5_000)
            cancellation_call_safe = hello_recovery.evaluate(
                "JSON.stringify(window.__HELLO_COMMIT_CALLS__) === '[false]'"
            )
            cancellation_focus_safe = hello_recovery.evaluate(
                "document.activeElement?.textContent?.trim() === 'Use Windows password recovery'"
            )
            cancellation_safe = escaped and cancellation_call_safe and cancellation_focus_safe
            recovery.click()
            dialog.wait_for(timeout=5_000)
            hello_recovery.get_by_role("button", name="Confirm recovery", exact=True).click()
            hello_recovery.wait_for_function("window.__HELLO_COMMIT_CALLS__.length === 2", timeout=5_000)
            busy_safe = (
                hello_recovery.get_by_role("button", name="Keep application locked", exact=True).is_disabled()
                and hello_recovery.get_by_role("button", name="Confirm recovery", exact=True).is_disabled()
                and hello_recovery.locator(".locked-surface-content button")
                .filter(has_text="Checking Windows Hello…")
                .is_disabled()
                and hello_recovery.locator(".locked-surface-content button")
                .filter(has_text="Use Windows password recovery")
                .is_disabled()
            )
            dialog.press("Escape")
            hello_recovery.wait_for_timeout(50)
            single_commit = hello_recovery.evaluate("JSON.stringify(window.__HELLO_COMMIT_CALLS__) === '[false,true]'")
            hello_recovery.evaluate("window.__HELLO_RESOLVE_COMMIT__()")
            try:
                hello_recovery.locator(".application-shell[data-application-ready]").wait_for(timeout=5_000)
            except PlaywrightError:
                details["applicationHelloRecoveryDiagnostics"] = hello_recovery.evaluate(
                    "() => ({body: document.body.innerText, calls: window.__HELLO_COMMIT_CALLS__})"
                )
            unlocked_after_core_ready = hello_recovery.locator("[data-application-locked]").count() == 0
            no_deferred_shortcut_dialog = hello_recovery.locator('[role="dialog"]').count() == 0
            details["applicationHelloRecoveryCases"] = {
                "retryVisible": retry_visible,
                "modalFocus": modal_focus,
                "modalBackgroundInert": modal_background_inert,
                "globalShortcutsSuppressed": global_shortcuts_suppressed,
                "cancellationSafe": cancellation_safe,
                "escapeClosed": escaped,
                "cancellationCallSafe": cancellation_call_safe,
                "cancellationFocusSafe": cancellation_focus_safe,
                "busySafe": busy_safe,
                "singleCommit": single_commit,
                "unlockedAfterCoreReady": unlocked_after_core_ready,
                "noDeferredShortcutDialog": no_deferred_shortcut_dialog,
            }
            details["applicationHelloRecovery"] = (
                retry_visible
                and modal_focus
                and modal_background_inert
                and global_shortcuts_suppressed
                and cancellation_safe
                and busy_safe
                and single_commit
                and unlocked_after_core_ready
                and no_deferred_shortcut_dialog
            )
            if hello_recovery_errors:
                errors.append(f"desktop Hello recovery runtime error: {'; '.join(hello_recovery_errors)}")
            hello_recovery.close()

            for width, height in ((1280, 720), (720, 450)):
                responsive = browser_context.new_page()
                responsive.set_viewport_size({"width": width, "height": height})
                responsive.goto("http://tauri.localhost/index.html", wait_until="load")
                responsive.wait_for_function("document.body.dataset.applicationReady === 'true'", timeout=5_000)
                overflow = responsive.evaluate(
                    "document.documentElement.scrollWidth > document.documentElement.clientWidth"
                )
                if overflow:
                    errors.append(f"desktop product overflows horizontally at {width}x{height}")
                details["responsiveCases"] += 1
                responsive.close()
        except (OSError, PlaywrightError, ValueError) as exc:
            errors.append(f"desktop product browser check failed: {exc}")
        finally:
            browser_context.close()
            browser.close()
    if details["requests"]:
        errors.append("desktop product attempted an unexpected network or local resource request")
    if details["referenceOnlyPages"] != 0:
        errors.append("desktop product exposes reference-only routes or workflow fixtures")
    for field in (
        "commandFocus",
        "skipLink",
        "shortcutDialog",
        "focusContainment",
        "focusRestoration",
        "focusVisible",
        "keyboardCommand",
        "homeShortcut",
        "themeToggle",
        "liveRegion",
        "boundaryState",
        "boundaryRecovery",
        "retainedInput",
        "diagnosticCopy",
        "diagnosticsUnavailable",
        "diagnosticsPreview",
        "diagnosticsTraceLink",
        "diagnosticsExactExport",
        "projectsWorkflow",
        "workflowProfileMatrixValid",
        "workflowEarlierStageRevisit",
        "adaptiveWorkflowNavigation",
        "intentMutationRaceGuarded",
        "privacySettingsWorkflow",
        "applicationLock",
        "applicationLockEventAclStartup",
        "applicationLockReconciliation",
        "applicationSettingsDraftReconciliation",
        "applicationSettingsConflictAnnouncement",
        "applicationSettingsPositionPreserved",
        "intentStoppingEffects",
        "applicationSettingsFocusRestoration",
        "applicationHelloRecovery",
    ):
        if details[field] is not True:
            errors.append(f"desktop product did not verify {field}")
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
                errors.append("desktop verification did not target the built reference-conformance fixture")
            frame_errors, frame = runtime_frame_errors(repo)
            errors.extend(frame_errors)
        except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(str(exc))
    return {"ok": not errors, "commands": commands, "errors": errors, "frame": frame}


def validate_built_frame(repo: Path) -> dict[str, Any]:
    """Validate the already-built functional product without replaying unrelated toolchain commands."""

    errors = [*security_errors(repo), *design_system_errors(repo)]
    frame: dict[str, Any] = {}
    if not errors:
        try:
            context = load_context(repo)
            if context.config["mode"] != "approved-reference-application":
                errors.append("desktop verification did not target the built reference-conformance fixture")
            frame_errors, frame = runtime_frame_errors(repo)
            errors.extend(frame_errors)
        except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(str(exc))
    return {"ok": not errors, "commands": [], "errors": errors, "frame": frame}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--built-frame-only",
        action="store_true",
        help="validate the existing functional product build without replaying the full desktop command plan",
    )
    args = parser.parse_args()
    repo = args.repo.resolve(strict=True)
    try:
        report = validate_built_frame(repo) if args.built_frame_only else validate(repo)
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
