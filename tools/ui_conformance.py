#!/usr/bin/env python3
"""Validate desktop UI conformance against the approved experience reference."""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.metadata
import json
import mimetypes
import os
import platform
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import yaml
from bs4 import BeautifulSoup, Tag
from jsonschema import Draft202012Validator
from playwright.sync_api import Browser, Page, ViewportSize, sync_playwright
from ui_reference_check import validate as validate_reference

CHECKS = frozenset({"tokens", "routes", "workflows", "accessibility", "visual"})
UI_SUFFIXES = frozenset(
    {
        ".css",
        ".html",
        ".js",
        ".jpeg",
        ".jpg",
        ".json",
        ".jsx",
        ".mjs",
        ".png",
        ".scss",
        ".svg",
        ".ts",
        ".tsx",
        ".webp",
        ".woff",
        ".woff2",
    }
)
TEST_SUFFIXES = (
    ".d.ts",
    ".spec.js",
    ".spec.jsx",
    ".spec.ts",
    ".spec.tsx",
    ".test.js",
    ".test.jsx",
    ".test.ts",
    ".test.tsx",
)
COMMON_SELECTORS = {
    "top bar": "header.topbar",
    "primary navigation": "aside.sidebar",
    "main region": "main#main-content",
    "workflow navigation": "[data-workflow-nav]",
    "supporting tools": "[data-all-tools]",
    "workflow context": "[data-workflow-context]",
    "theme control": "[data-theme-toggle]",
    "sidebar control": "[data-sidebar-toggle]",
    "workflow selector": "[data-workflow-select]",
}
TOKEN_PATTERN = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;{}]+);", flags=re.IGNORECASE)
WORKFLOW_CONTEXT_EXCLUSIONS = frozenset(
    {"project-home", "projects", "new-project", "intent-contract", "prototype-index", "style-guide"}
)
Theme = Literal["light", "dark"]
BASELINE_KEYS = frozenset(
    {
        "schemaVersion",
        "documentType",
        "referenceId",
        "referencePackageSha256",
        "referenceApprovalCommit",
        "platform",
        "playwrightVersion",
        "browserVersion",
        "settings",
        "entries",
    }
)
BASELINE_ENTRY_KEYS = frozenset({"page", "theme", "width", "height", "sha256"})


@dataclass(frozen=True)
class Context:
    repo: Path
    config: dict[str, Any]
    reference: Path
    target: Path
    site: dict[str, Any]
    workflows: dict[str, Any]
    pages: list[str]


def confined_path(repo: Path, relative: str, *, must_exist: bool = True) -> Path:
    if not relative or "\\" in relative or relative.startswith("/") or ".." in Path(relative).parts:
        raise ValueError(f"noncanonical repository path: {relative!r}")
    candidate = (repo / relative).absolute()
    resolved = candidate.resolve(strict=must_exist)
    resolved.relative_to(repo)
    if candidate != resolved or candidate.is_symlink() or candidate.is_junction():
        raise ValueError(f"redirected repository path: {relative}")
    return candidate


def json_object(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return loaded


def implementation_files(repo: Path, roots: list[str]) -> list[str]:
    found: list[str] = []

    def fail_closed(error: OSError) -> None:
        raise error

    for root in roots:
        root_path = confined_path(repo, root, must_exist=False)
        if not root_path.exists():
            continue
        for directory, child_directories, file_names in os.walk(root_path, followlinks=False, onerror=fail_closed):
            directory_path = Path(directory)
            for name in [*child_directories, *file_names]:
                candidate = directory_path / name
                relative = candidate.relative_to(repo).as_posix()
                confined_path(repo, relative)
            for name in file_names:
                path = directory_path / name
                relative = path.relative_to(repo).as_posix()
                if path.suffix.lower() in UI_SUFFIXES and not relative.endswith(TEST_SUFFIXES):
                    found.append(relative)
    return sorted(found)


def load_context(repo: Path) -> Context:
    repo = repo.resolve(strict=True)
    config_path = confined_path(repo, "verification/extensions/desktop-ui.json")
    schema_path = confined_path(repo, "verification/desktop-ui.schema.json")
    config = json_object(config_path)
    schema = json_object(schema_path)
    issues = sorted(Draft202012Validator(schema).iter_errors(config), key=lambda issue: list(issue.absolute_path))
    if issues:
        details = "; ".join(
            f"{'.'.join(str(part) for part in issue.absolute_path) or '<root>'}: {issue.message}" for issue in issues
        )
        raise ValueError(f"invalid desktop UI activation: {details}")
    reference = confined_path(repo, str(config["referenceRoot"]))
    target = confined_path(repo, str(config["targetRoot"]))
    reference_result = validate_reference(reference, None)
    if not reference_result["ok"]:
        raise ValueError("approved UI reference is invalid: " + "; ".join(reference_result["errors"]))
    if reference_result["reference_id"] != config["referenceId"]:
        raise ValueError("desktop UI activation reference ID does not match the approved reference")
    if reference_result["reference_package_sha256"] != config["referencePackageSha256"]:
        raise ValueError("desktop UI activation package SHA-256 does not match the approved reference")
    if config["mode"] == "approved-reference-fixture":
        found = implementation_files(repo, list(config["implementationRoots"]))
        if found:
            raise ValueError(
                "approved-reference-fixture mode cannot remain active after desktop UI implementation appears: "
                + ", ".join(found)
            )
    site = json_object(confined_path(reference, "SITE_MANIFEST.json"))
    workflow_document = json_object(confined_path(reference, "WORKFLOW_CATALOG.json"))
    workflows = workflow_document.get("workflows")
    if not isinstance(workflows, dict):
        raise ValueError("WORKFLOW_CATALOG.json workflows must be an object")
    page_items = site.get("pages")
    if not isinstance(page_items, list):
        raise ValueError("SITE_MANIFEST.json pages must be an array")
    pages = [str(item.get("file")) for item in page_items if isinstance(item, dict)]
    if len(pages) != 32 or len(set(pages)) != 32 or any(not page.endswith(".html") for page in pages):
        raise ValueError("approved desktop route inventory must contain exactly 32 unique HTML product pages")
    return Context(repo, config, reference, target, site, workflows, pages)


def source(context: Context, key: str) -> str:
    return str(context.config["normativeSources"][key])


def result(context: Context, check: str, errors: list[str], details: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "documentType": "desktop-ui-conformance-report",
        "check": check,
        "ok": not errors,
        "mode": context.config["mode"],
        "referenceId": context.config["referenceId"],
        "referencePackageSha256": context.config["referencePackageSha256"],
        "normativeSources": context.config["normativeSources"],
        "illustrativeExclusions": context.config["illustrativeExclusions"],
        "details": details,
        "errors": errors,
    }


def token_map(path: Path) -> dict[str, list[str]]:
    text = path.read_text(encoding="utf-8")
    tokens: dict[str, list[str]] = {}
    for name, value in TOKEN_PATTERN.findall(text):
        tokens.setdefault(name.lower(), []).append(re.sub(r"\s+", " ", value.strip()).lower())
    return tokens


def check_tokens(context: Context) -> dict[str, Any]:
    errors: list[str] = []
    reference_path = confined_path(context.reference, "assets/tokens.css")
    target_path = confined_path(context.target, "assets/tokens.css")
    expected = token_map(reference_path)
    observed = token_map(target_path)
    if expected != observed:
        missing = sorted(set(expected) - set(observed))
        extra = sorted(set(observed) - set(expected))
        changed = sorted(name for name in set(expected) & set(observed) if expected[name] != observed[name])
        errors.append(
            f"{source(context, 'tokens')}: semantic token drift; missing={missing}, extra={extra}, changed={changed}"
        )
    # The approved fixture contains component-local and illustrative custom properties
    # (for example chart geometry) in addition to normative semantic tokens.  Exact
    # token parity is the pre-application contract; application mode must replace
    # this fixture activation and may add implementation-specific token-use linting.
    unresolved: list[str] = []
    required = {"--canvas", "--surface-1", "--text-strong", "--brand-600", "--focus-ring", "--transition-default"}
    if not required <= set(observed):
        errors.append(f"{source(context, 'tokens')}: required semantic token set is incomplete")
    return result(context, "tokens", errors, {"tokens": len(observed), "undefinedReferences": unresolved})


def soup(path: Path) -> BeautifulSoup:
    return BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")


def check_routes(context: Context) -> dict[str, Any]:
    errors: list[str] = []
    page_ids: set[str] = set()
    linked_routes: set[str] = set()
    for page_name in context.pages:
        reference_page = soup(confined_path(context.reference, page_name))
        target_page = soup(confined_path(context.target, page_name))
        expected_id = str(reference_page.body.get("data-page", "")) if reference_page.body else ""
        observed_id = str(target_page.body.get("data-page", "")) if target_page.body else ""
        if not observed_id or observed_id != expected_id or observed_id in page_ids:
            errors.append(
                f"{source(context, 'routes')}#{page_name}: route identity must be unique and match {expected_id!r}"
            )
        page_ids.add(observed_id)
        for label, selector in COMMON_SELECTORS.items():
            if target_page.select_one(selector) is None:
                errors.append(f"{source(context, 'pages')}#{page_name}: missing required {label} region {selector}")
        reference_tools = reference_page.select_one("[data-all-tools]")
        target_tools = target_page.select_one("[data-all-tools]")
        expected_hrefs = (
            [str(link.get("href")) for link in reference_tools.select("a[href]")]
            if isinstance(reference_tools, Tag)
            else []
        )
        observed_hrefs = (
            [str(link.get("href")) for link in target_tools.select("a[href]")] if isinstance(target_tools, Tag) else []
        )
        if observed_hrefs != expected_hrefs:
            errors.append(
                f"{source(context, 'routes')}#{page_name}: supporting-tool navigation differs from the approved order"
            )
        linked_routes.update(
            str(link.get("href")) for link in target_page.select("a[href]") if str(link.get("href")) in context.pages
        )
    entry_points = context.site.get("entry_points")
    if isinstance(entry_points, dict):
        for value in entry_points.values():
            page_name = str(value)
            if not page_name.endswith(".html"):
                continue
            entry_page = soup(confined_path(context.target, page_name))
            linked_routes.update(
                str(link.get("href")) for link in entry_page.select("a[href]") if str(link.get("href")) in context.pages
            )
    unreachable = sorted(set(context.pages) - linked_routes - {"index.html"})
    if unreachable:
        errors.append(
            f"{source(context, 'routes')}: product routes lack an incoming local navigation link: {unreachable}"
        )
    return result(
        context,
        "routes",
        errors,
        {"routes": len(context.pages), "uniqueRouteIds": len(page_ids), "requiredRegions": sorted(COMMON_SELECTORS)},
    )


def inline_page(
    context: Context,
    page_name: str,
    theme: Theme = "light",
    root: Path | None = None,
) -> str:
    source_root = root or context.target
    path = confined_path(source_root, page_name)
    document = soup(path)
    if document.html is None or document.head is None or document.body is None:
        raise ValueError(f"target page is not a complete HTML document: {page_name}")
    document.html["data-theme"] = theme
    for tag in list(document.find_all("link", rel="stylesheet")):
        tag.decompose()
    styles = "\n".join(
        confined_path(source_root, relative).read_text(encoding="utf-8")
        for relative in ("assets/tokens.css", "assets/app.css")
    )
    freeze = "*{animation:none!important;transition:none!important;caret-color:transparent!important}"
    style = document.new_tag("style")
    style.string = styles + "\n" + freeze
    document.head.append(style)
    for tag in list(document.find_all("script", src=True)):
        tag.decompose()
    script = document.new_tag("script")
    script.string = confined_path(source_root, "assets/app.js").read_text(encoding="utf-8")
    document.body.append(script)
    for image in document.find_all("img", src=True):
        raw = str(image.get("src", ""))
        if raw.startswith("data:"):
            continue
        image_path = confined_path(source_root, str((Path(page_name).parent / raw).as_posix()))
        mime = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
        image["src"] = f"data:{mime};base64,{base64.b64encode(image_path.read_bytes()).decode('ascii')}"
    return str(document)


def open_browser(context: Context) -> tuple[Any, Browser]:
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(
        headless=True,
        args=["--disable-font-subpixel-positioning", "--disable-lcd-text", "--force-color-profile=srgb"],
    )
    return playwright, browser


def new_page(
    browser: Browser,
    context: Context,
    viewport: ViewportSize | None = None,
    theme: Theme = "light",
) -> Page:
    visual = context.config["visual"]
    configured_viewport = visual["viewport"]
    selected_viewport: ViewportSize = viewport or {
        "width": int(configured_viewport["width"]),
        "height": int(configured_viewport["height"]),
    }
    browser_context = browser.new_context(
        viewport=selected_viewport,
        device_scale_factor=visual["deviceScaleFactor"],
        locale=visual["locale"],
        timezone_id=visual["timezoneId"],
        reduced_motion=visual["reducedMotion"],
        color_scheme=theme,
    )
    browser_context.route("**/*", lambda route: route.abort())
    page = browser_context.new_page()
    page.add_init_script(
        """
        Date = class extends Date { constructor(...a){ super(...(a.length ? a : ['2026-08-08T12:00:00Z'])); }
          static now(){ return 1786190400000; } };
        Math.random = () => 0.25;
        """
    )
    return page


def set_page(page: Page, context: Context, page_name: str, theme: Theme = "light") -> None:
    page.set_content(inline_page(context, page_name, theme), wait_until="load")
    page.locator("html").evaluate("(node, value) => node.dataset.theme = value", theme)
    page.emulate_media(color_scheme=theme, reduced_motion="reduce")
    page.evaluate("document.fonts.ready")


def check_workflows(context: Context) -> dict[str, Any]:
    errors: list[str] = []
    if len(context.workflows) != 14:
        errors.append(f"{source(context, 'workflows')}: expected exactly 14 workflow profiles")
    playwright, browser = open_browser(context)
    cases = 0
    repeated_routes: dict[str, list[str]] = {}
    try:
        for workflow_id, specification in sorted(context.workflows.items()):
            steps = specification.get("steps") if isinstance(specification, dict) else None
            if not isinstance(steps, list) or not steps:
                errors.append(f"{source(context, 'workflows')}#{workflow_id}: steps must be a non-empty array")
                continue
            page = new_page(browser, context)
            try:
                set_page(page, context, "index.html")
                page.select_option("[data-workflow-select]", workflow_id)
                observed = page.locator("[data-workflow-nav] a").evaluate_all(
                    "nodes => nodes.map(node => node.getAttribute('href'))"
                )
                if observed != steps:
                    errors.append(f"{source(context, 'workflows')}#{workflow_id}: ordered primary navigation differs")
                seen_step_pages: set[str] = set()
                for index in range(len(steps)):
                    step_page = str(steps[index])
                    if step_page in seen_step_pages:
                        repeated_routes.setdefault(workflow_id, []).append(step_page)
                        continue
                    seen_step_pages.add(step_page)
                    set_page(page, context, step_page)
                    page.select_option("[data-workflow-select]", workflow_id)
                    page_id = page.locator("body").get_attribute("data-page")
                    if page_id in WORKFLOW_CONTEXT_EXCLUSIONS:
                        continue
                    hrefs = page.locator("[data-workflow-context] a").evaluate_all(
                        "nodes => nodes.map(node => node.getAttribute('href'))"
                    )
                    expected: list[str] = []
                    if index > 0:
                        expected.append(str(steps[index - 1]))
                    expected.append(str(steps[index + 1]) if index + 1 < len(steps) else "index.html")
                    if hrefs != expected:
                        errors.append(
                            f"{source(context, 'workflows')}#{workflow_id}:{steps[index]}: previous/next links "
                            f"must be {expected}; found {hrefs}"
                        )
                    cases += 1
                supporting = None
                for name in context.pages:
                    candidate = soup(confined_path(context.target, name))
                    page_id = str(candidate.body.get("data-page", "")) if candidate.body else ""
                    if name not in steps and name != "index.html" and page_id not in WORKFLOW_CONTEXT_EXCLUSIONS:
                        supporting = name
                        break
                if supporting:
                    set_page(page, context, supporting)
                    page.select_option("[data-workflow-select]", workflow_id)
                    if not page.locator("[data-workflow-context]").evaluate(
                        "node => node.classList.contains('supporting')"
                    ):
                        errors.append(
                            f"{source(context, 'workflows')}#{workflow_id}:{supporting}: "
                            "supporting-tool context is absent"
                        )
                    cases += 1
            finally:
                page.context.close()
    finally:
        browser.close()
        playwright.stop()
    return result(
        context,
        "workflows",
        errors,
        {"profiles": len(context.workflows), "browserCases": cases, "approvedRepeatedRoutes": repeated_routes},
    )


def accessible_name(element: Tag) -> str:
    label = element.find_parent("label")
    return " ".join(
        str(value).strip()
        for value in (
            element.get("aria-label"),
            element.get("title"),
            element.get("alt"),
            element.get("value") if element.name in {"button", "input"} else None,
            element.get("placeholder"),
            label.get_text(" ", strip=True) if label else None,
            element.get_text(" ", strip=True),
        )
        if value
    ).strip()


def check_accessibility(context: Context) -> dict[str, Any]:
    errors: list[str] = []
    for page_name in context.pages:
        document = soup(confined_path(context.target, page_name))
        ids = [str(tag.get("id")) for tag in document.select("[id]")]
        duplicates = sorted({value for value in ids if ids.count(value) > 1})
        if duplicates:
            errors.append(f"{source(context, 'pages')}#{page_name}: duplicate IDs {duplicates}")
        if not document.html or document.html.get("lang") != "en":
            errors.append(f"{source(context, 'style')}#{page_name}: document language must be en")
        reference = soup(confined_path(context.reference, page_name))
        expected_h1 = len(reference.find_all("h1"))
        if len(document.find_all("h1")) != expected_h1:
            errors.append(
                f"{source(context, 'pages')}#{page_name}: h1 count differs from approved page contract ({expected_h1})"
            )
        interactive_selector = "a[href], button, summary, input, select, textarea"
        expected_names = [accessible_name(element) for element in reference.select(interactive_selector)]
        observed_names = [accessible_name(element) for element in document.select(interactive_selector)]
        if observed_names != expected_names:
            errors.append(f"{source(context, 'style')}#{page_name}: interactive accessible names differ from reference")
        for element in document.select(interactive_selector):
            if element.get("type") == "hidden":
                continue
            if not accessible_name(element):
                errors.append(f"{source(context, 'style')}#{page_name}: unnamed interactive <{element.name}>")
        for image in document.find_all("img"):
            if image.get("alt") is None:
                errors.append(f"{source(context, 'style')}#{page_name}: image lacks alt text")
    css = confined_path(context.target, "assets/app.css").read_text(encoding="utf-8")
    if ":focus-visible" not in css or "var(--focus-ring)" not in css:
        errors.append(f"{source(context, 'style')}: visible focus-ring contract is missing")
    if "prefers-reduced-motion: reduce" not in css:
        errors.append(f"{source(context, 'style')}: reduced-motion contract is missing")
    playwright, browser = open_browser(context)
    responsive_cases = 0
    try:
        page = new_page(browser, context)
        try:
            set_page(page, context, "index.html")
            page.keyboard.press("Tab")
            focus = page.evaluate(
                """() => { const e=document.activeElement; const s=getComputedStyle(e); return {
                  tag:e?.tagName, shadow:s.boxShadow, outline:s.outlineStyle}; }"""
            )
            if not focus.get("tag") or (focus.get("shadow") == "none" and focus.get("outline") in {"none", ""}):
                errors.append(f"{source(context, 'style')}: keyboard focus is not visibly rendered")
            theme = page.locator("html").get_attribute("data-theme")
            page.locator("[data-theme-toggle]").focus()
            page.keyboard.press("Enter")
            if page.locator("html").get_attribute("data-theme") == theme:
                errors.append(f"{source(context, 'style')}: keyboard theme activation failed")
            page.locator("[data-sidebar-toggle]").focus()
            page.keyboard.press("Enter")
            if not page.locator("body").evaluate("node => node.classList.contains('sidebar-collapsed')"):
                errors.append(f"{source(context, 'style')}: keyboard sidebar activation failed")
        finally:
            page.context.close()
        for viewport in context.config["visual"]["responsiveViewports"]:
            page = new_page(browser, context, {"width": viewport["width"], "height": viewport["height"]})
            reference_page = new_page(browser, context, {"width": viewport["width"], "height": viewport["height"]})
            try:
                for page_name in context.pages:
                    set_page(page, context, page_name)
                    reference_html = inline_page(context, page_name, root=context.reference)
                    reference_page.set_content(reference_html, wait_until="load")
                    overflow = page.evaluate(
                        "document.documentElement.scrollWidth > document.documentElement.clientWidth + 1"
                    )
                    expected_overflow = reference_page.evaluate(
                        "document.documentElement.scrollWidth > document.documentElement.clientWidth + 1"
                    )
                    if overflow != expected_overflow:
                        errors.append(
                            f"{source(context, 'style')}#{page_name}: responsive overflow differs from reference "
                            f"at {viewport['label']}"
                        )
                    responsive_cases += 1
            finally:
                reference_page.context.close()
                page.context.close()
    finally:
        browser.close()
        playwright.stop()
    return result(
        context,
        "accessibility",
        errors,
        {
            "pages": len(context.pages),
            "responsiveCases": responsive_cases,
            "standard": "approved-reference accessibility and responsive contract",
        },
    )


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False, timeout=30)
    if completed.returncode != 0:
        raise ValueError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed.stdout.strip()


def baseline_document_errors(value: dict[str, Any], label: str) -> list[str]:
    errors: list[str] = []
    keys = set(value)
    if keys != BASELINE_KEYS:
        errors.append(
            f"{label}: baseline fields must be exact; missing={sorted(BASELINE_KEYS - keys)}, "
            f"extra={sorted(keys - BASELINE_KEYS)}"
        )
    if value.get("schemaVersion") != "1.0" or value.get("documentType") != "desktop-ui-visual-baseline":
        errors.append(f"{label}: baseline document identity is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(value.get("referencePackageSha256", ""))):
        errors.append(f"{label}: referencePackageSha256 must be lowercase SHA-256")
    if not re.fullmatch(r"[0-9a-f]{40}", str(value.get("referenceApprovalCommit", ""))):
        errors.append(f"{label}: referenceApprovalCommit must be a full commit SHA")
    entries = value.get("entries")
    if not isinstance(entries, dict) or not entries:
        errors.append(f"{label}: entries must be a non-empty object")
        return errors
    for key, raw_entry in entries.items():
        entry_label = f"{label}#{key}"
        if not isinstance(key, str) or not isinstance(raw_entry, dict):
            errors.append(f"{entry_label}: visual entry must be an object")
            continue
        if set(raw_entry) != BASELINE_ENTRY_KEYS:
            errors.append(f"{entry_label}: visual entry fields must be exact")
            continue
        page_name = raw_entry.get("page")
        theme = raw_entry.get("theme")
        if key != f"{page_name}::{theme}" or theme not in {"light", "dark"}:
            errors.append(f"{entry_label}: visual entry key, page, and theme are inconsistent")
        if not isinstance(raw_entry.get("width"), int) or not isinstance(raw_entry.get("height"), int):
            errors.append(f"{entry_label}: visual dimensions must be integers")
        if not re.fullmatch(r"[0-9a-f]{64}", str(raw_entry.get("sha256", ""))):
            errors.append(f"{entry_label}: screenshot SHA-256 is invalid")
    return errors


def git_json_at(repo: Path, revision: str, relative: str) -> tuple[dict[str, Any] | None, str | None, str | None]:
    listing = subprocess.run(
        ["git", "ls-tree", revision, "--", relative],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if listing.returncode != 0:
        return None, None, f"cannot inspect {revision}:{relative}"
    if not listing.stdout.strip():
        return None, None, None
    metadata, separator, path = listing.stdout.strip().partition("\t")
    fields = metadata.split()
    if (
        not separator
        or path != relative
        or len(fields) != 3
        or fields[0] not in {"100644", "100755"}
        or fields[1] != "blob"
    ):
        return None, None, f"{revision}:{relative} must be a regular Git blob"
    payload = git(repo, "show", f"{revision}:{relative}")
    try:
        loaded = json.loads(payload)
    except json.JSONDecodeError as exc:
        return None, payload, f"{revision}:{relative}: invalid JSON: {exc.msg}"
    if not isinstance(loaded, dict):
        return None, payload, f"{revision}:{relative}: baseline must be an object"
    return loaded, payload, None


def approval_lineage_errors(repo: Path, baseline: dict[str, Any], baseline_commit: str) -> list[str]:
    errors: list[str] = []
    approval_commit = str(baseline.get("referenceApprovalCommit", ""))
    if not re.fullmatch(r"[0-9a-f]{40}", approval_commit):
        return errors
    try:
        resolved = git(repo, "rev-parse", "--verify", f"{approval_commit}^{{commit}}")
    except ValueError:
        return [f"{baseline_commit}: reference approval commit cannot be resolved"]
    if resolved != approval_commit:
        errors.append(f"{baseline_commit}: reference approval must use an exact full commit SHA")
        return errors
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", approval_commit, baseline_commit],
        cwd=repo,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if approval_commit == baseline_commit or ancestor.returncode != 0:
        errors.append(f"{baseline_commit}: approved reference must strictly precede the visual baseline")
    changed = git(
        repo,
        "diff-tree",
        "--root",
        "--no-commit-id",
        "--name-only",
        "-r",
        approval_commit,
    ).splitlines()
    if "design/ui-reference/APPROVAL.yaml" not in changed:
        errors.append(f"{baseline_commit}: cited reference approval commit did not change APPROVAL.yaml")
        return errors
    try:
        approval = yaml.safe_load(git(repo, "show", f"{approval_commit}:design/ui-reference/APPROVAL.yaml"))
    except ValueError, yaml.YAMLError:
        return [*errors, f"{baseline_commit}: cited reference approval record is unreadable"]
    if not isinstance(approval, dict) or approval.get("status") != "approved":
        errors.append(f"{baseline_commit}: cited reference approval record is not approved")
    elif approval.get("reference_id") != baseline.get("referenceId"):
        errors.append(f"{baseline_commit}: baseline referenceId differs from its cited approval record")
    return errors


def render_visuals(context: Context) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    visual = context.config["visual"]
    if platform.system() != "Windows" or platform.machine().lower() not in {"amd64", "x86_64"}:
        return {}, [f"{source(context, 'style')}: visual baseline requires controlled windows-x64"]
    installed = importlib.metadata.version("playwright")
    if installed != visual["playwrightVersion"]:
        return {}, [
            f"{source(context, 'style')}: Playwright must equal {visual['playwrightVersion']}; found {installed}"
        ]
    entries: dict[str, Any] = {}
    playwright, browser = open_browser(context)
    try:
        if browser.version != visual["browserVersion"]:
            errors.append(
                f"{source(context, 'style')}: Chromium must equal {visual['browserVersion']}; found {browser.version}"
            )
        for theme in visual["colorSchemes"]:
            page = new_page(browser, context, theme=theme)
            try:
                for page_name in context.pages:
                    set_page(page, context, page_name, theme)
                    missing_fonts = [
                        font
                        for font in visual["requiredFonts"]
                        if not page.evaluate('font => document.fonts.check(`12px \\"${font}\\"`)', font)
                    ]
                    if missing_fonts:
                        errors.append(
                            f"{source(context, 'style')}#{page_name}: missing controlled fonts {missing_fonts}"
                        )
                        continue
                    payload = page.screenshot(
                        full_page=False,
                        animations="disabled",
                        caret="hide",
                        scale="device",
                    )
                    key = f"{page_name}::{theme}"
                    entries[key] = {
                        "page": page_name,
                        "theme": theme,
                        "width": visual["viewport"]["width"],
                        "height": visual["viewport"]["height"],
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
            finally:
                page.context.close()
    finally:
        browser.close()
        playwright.stop()
    return dict(sorted(entries.items())), errors


def baseline_history_errors(context: Context, baseline: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    relative = str(context.config["visual"]["baselinePath"])
    if git(context.repo, "rev-parse", "--is-inside-work-tree") != "true":
        return [f"{relative}: cannot inspect governed Git history"]
    if git(context.repo, "rev-parse", "--is-shallow-repository") == "true":
        return [f"{relative}: visual baseline history requires a complete, non-shallow checkout"]
    status = git(context.repo, "status", "--porcelain=v1", "--", relative)
    if status:
        errors.append(f"{relative}: visual baseline must be committed before authoritative verification")
    head = git(context.repo, "rev-parse", "--verify", "HEAD")
    head_baseline, _, head_error = git_json_at(context.repo, head, relative)
    if head_error:
        errors.append(head_error)
    elif head_baseline is None:
        errors.append(f"{relative}: visual baseline is absent from HEAD")
    elif head_baseline != baseline:
        errors.append(f"{relative}: working baseline bytes differ from the committed HEAD baseline")

    commits = git(context.repo, "rev-list", "--reverse", "--topo-order", head).splitlines()
    snapshots: dict[str, tuple[dict[str, Any] | None, str | None]] = {}
    identities: dict[tuple[str, str], dict[str, str]] = {}

    def snapshot(revision: str) -> tuple[dict[str, Any] | None, str | None]:
        if revision not in snapshots:
            value, payload, read_error = git_json_at(context.repo, revision, relative)
            snapshots[revision] = (value, payload)
            if read_error:
                errors.append(read_error)
        return snapshots[revision]

    for commit in commits:
        current, current_payload = snapshot(commit)
        parents = git(context.repo, "rev-list", "--parents", "-n", "1", commit).split()[1:]
        if current is not None:
            errors.extend(baseline_document_errors(current, f"{commit}:{relative}"))
            errors.extend(approval_lineage_errors(context.repo, current, commit))
            identity = (str(current.get("referenceId", "")), str(current.get("referenceApprovalCommit", "")))
            if current_payload is not None:
                blob = hashlib.sha256(current_payload.encode("utf-8")).hexdigest()
                identities.setdefault(identity, {}).setdefault(blob, commit)
        for parent in parents or [""]:
            previous, previous_payload = snapshot(parent) if parent else (None, None)
            edge = f"{commit}<-{parent or '<root>'}"
            if previous is not None and current is None:
                errors.append(f"{edge}: visual baseline was removed from reachable history")
                continue
            if previous is None or current is None or previous_payload == current_payload:
                continue
            if current.get("referenceId") == previous.get("referenceId"):
                errors.append(f"{edge}: changing a visual baseline requires a new approved reference ID")
            if current.get("referenceApprovalCommit") == previous.get("referenceApprovalCommit"):
                errors.append(f"{edge}: changing a visual baseline requires a new reference approval commit")
            prior_change = git(context.repo, "log", "-1", "--format=%H", parent, "--", relative)
            approval_commit = str(current.get("referenceApprovalCommit", ""))
            if prior_change and re.fullmatch(r"[0-9a-f]{40}", approval_commit):
                prior_is_ancestor = subprocess.run(
                    ["git", "merge-base", "--is-ancestor", prior_change, approval_commit],
                    cwd=context.repo,
                    capture_output=True,
                    check=False,
                    timeout=30,
                )
                if approval_commit == prior_change or prior_is_ancestor.returncode != 0:
                    errors.append(f"{edge}: new reference approval must follow the prior baseline version")
    for identity, blobs in sorted(identities.items()):
        if len(blobs) > 1:
            details = ", ".join(f"{blob}@{commit}" for blob, commit in sorted(blobs.items()))
            errors.append(f"{relative}: baseline identity {identity} has multiple reachable blobs: {details}")
    return errors


def check_visual(context: Context) -> dict[str, Any]:
    errors: list[str] = []
    baseline_path = confined_path(context.repo, str(context.config["visual"]["baselinePath"]))
    baseline = json_object(baseline_path)
    errors.extend(baseline_document_errors(baseline, baseline_path.relative_to(context.repo).as_posix()))
    errors.extend(baseline_history_errors(context, baseline))
    expected_identity = {
        "referenceId": context.config["referenceId"],
        "referencePackageSha256": context.config["referencePackageSha256"],
        "platform": context.config["visual"]["platform"],
        "playwrightVersion": context.config["visual"]["playwrightVersion"],
        "browserVersion": context.config["visual"]["browserVersion"],
        "settings": context.config["visual"],
    }
    for key, expected in expected_identity.items():
        if baseline.get(key) != expected:
            errors.append(f"{baseline_path.relative_to(context.repo).as_posix()}: {key} does not match activation")
    observed, render_errors = render_visuals(context)
    errors.extend(render_errors)
    if baseline.get("entries") != observed:
        raw_entries = baseline.get("entries")
        expected_entries = cast(dict[str, Any], raw_entries) if isinstance(raw_entries, dict) else {}
        changed = sorted(
            key for key in set(expected_entries) | set(observed) if expected_entries.get(key) != observed.get(key)
        )
        for key in changed:
            page_name = key.split("::", 1)[0]
            errors.append(f"{source(context, 'pages')}#{page_name}: visual baseline mismatch for {key}")
    return result(context, "visual", errors, {"captures": len(observed), "settings": context.config["visual"]})


def write_baseline(context: Context, approved_reference_id: str | None) -> dict[str, Any]:
    if approved_reference_id != context.config["referenceId"]:
        raise ValueError("--approved-reference-id must equal the exact approved reference ID")
    path = confined_path(context.repo, str(context.config["visual"]["baselinePath"]), must_exist=False)
    if path.exists():
        existing = json_object(path)
        if existing.get("referenceId") == context.config["referenceId"]:
            raise ValueError("refusing to rewrite a baseline for the same approved reference")
    entries, errors = render_visuals(context)
    if errors:
        raise ValueError("; ".join(errors))
    approval_commit = git(context.repo, "log", "-1", "--format=%H", "--", "design/ui-reference/APPROVAL.yaml")
    baseline = {
        "schemaVersion": "1.0",
        "documentType": "desktop-ui-visual-baseline",
        "referenceId": context.config["referenceId"],
        "referencePackageSha256": context.config["referencePackageSha256"],
        "referenceApprovalCommit": approval_commit,
        "platform": context.config["visual"]["platform"],
        "playwrightVersion": context.config["visual"]["playwrightVersion"],
        "browserVersion": context.config["visual"]["browserVersion"],
        "settings": context.config["visual"],
        "entries": entries,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        prefix=path.name,
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(json.dumps(baseline, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    try:
        if temporary.resolve(strict=True).parent != path.parent.resolve(strict=True):
            raise ValueError("visual baseline temporary escaped its canonical parent")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return baseline


def run_check(repo: Path, check: str) -> dict[str, Any]:
    context = load_context(repo)
    functions = {
        "tokens": check_tokens,
        "routes": check_routes,
        "workflows": check_workflows,
        "accessibility": check_accessibility,
        "visual": check_visual,
    }
    return functions[check](context)


def report_path(repo: Path, raw: Path) -> Path:
    root = confined_path(repo, "artifacts/tmp")
    destination = (raw if raw.is_absolute() else repo / raw).absolute()
    destination.parent.resolve(strict=True).relative_to(root)
    if destination.parent.resolve(strict=True) != destination.parent or destination.parent.is_junction():
        raise ValueError("desktop UI report parent is redirected")
    return destination


def cli(check: str | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--check", choices=sorted(CHECKS), default=check)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--approved-reference-id")
    args = parser.parse_args()
    repo = args.repo.resolve(strict=True)
    try:
        if args.write_baseline:
            context = load_context(repo)
            baseline = write_baseline(context, args.approved_reference_id)
            output: dict[str, Any] = {
                "ok": True,
                "check": "visual-baseline-write",
                "referenceId": baseline["referenceId"],
                "captures": len(baseline["entries"]),
                "errors": [],
            }
        else:
            selected = args.check
            if selected not in CHECKS:
                raise ValueError("one conformance --check is required")
            output = run_check(repo, selected)
        rendered = json.dumps(output, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        print(rendered, end="")
        if args.report:
            destination = report_path(repo, args.report)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="\n", dir=destination.parent, prefix=destination.name, delete=False
            ) as handle:
                temporary = Path(handle.name)
                handle.write(rendered)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        return 0 if output.get("ok") else 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(cli())
