#!/usr/bin/env python3
"""Build and validate the pinned offline Tauri/React desktop application."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
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
    "data-workflow-nav",
    "data-all-tools",
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
        "implementedCapabilities": ["CAP-01"],
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
        page for page in reference_pages - {"index.html"} if isinstance(page, str) and page in text_artifacts
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


def runtime_frame_errors(repo: Path) -> tuple[list[str], dict[str, Any]]:
    errors = product_build_errors(repo)
    runtime_path = repo / PRODUCT_ROOT / "assets" / "app.js"
    runtime = runtime_path.read_text(encoding="utf-8") if runtime_path.is_file() else ""
    if "process.env.NODE_ENV" in runtime:
        errors.append("desktop production runtime retains an unresolved Node environment expression")
    details: dict[str, Any] = {
        "pages": 0,
        "implementedCapabilities": ["CAP-01"],
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
        "responsiveCases": 0,
        "criticalViolations": [],
        "requests": [],
        "designSystem": {},
        "largeTable": {},
    }
    if errors:
        return errors, details
    document = inline_product_index(repo)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        browser_context = browser.new_context()

        def serve_application(route: Any) -> None:
            if route.request.url in {"http://tauri.localhost/", "http://tauri.localhost/index.html"}:
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=document)
            else:
                details["requests"].append(route.request.url)
                route.abort()

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
            details["referenceOnlyPages"] = page.locator(
                'a[href$=".html"], [data-workflow-select], [data-workflow-nav], [data-all-tools]'
            ).count()
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
            page.get_by_role("button", name="Diagnostics & support", exact=True).click()
            page.get_by_role("heading", name="Diagnostics unavailable").wait_for(state="visible", timeout=5_000)
            details["diagnosticsUnavailable"] = (
                page.locator("[data-diagnostics-workspace]").count() == 1
                and page.locator("h1").inner_text().strip() == "Diagnostics & support"
                and "No support data was exported" in page.locator("main").inner_text()
                and page.locator("[data-workflow-select], [data-workflow-nav], [data-all-tools]").count() == 0
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
                    byteLength: 2048,
                    sha256: 'b'.repeat(64),
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
                  window.__TAURI_INTERNALS__ = {
                    invoke: async (command, args) => {
                      if (command === 'core_runtime_start' || command === 'core_runtime_status') {
                        return {state: 'ready', attempt: 1, retryAvailable: false, diagnosticReference: null};
                      }
                      if (command === 'core_runtime_stop') return undefined;
                      if (command === 'support_bundle_preview') return preview;
                      if (command === 'support_bundle_export' && args?.previewId === preview.previewId) {
                        return {
                          bundleId: preview.bundle.bundleId,
                          path: 'C:\\Research Observatory\\support-exports\\bundle.json',
                          byteLength: preview.byteLength,
                          sha256: preview.sha256
                        };
                      }
                      throw new Error('unsupported test command');
                    }
                  };
                })()"""
            )
            diagnostics.goto("http://tauri.localhost/index.html", wait_until="load")
            diagnostics.wait_for_function("document.body.dataset.applicationReady === 'true'", timeout=5_000)
            diagnostics.get_by_role("button", name="Diagnostics & support", exact=True).click()
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
