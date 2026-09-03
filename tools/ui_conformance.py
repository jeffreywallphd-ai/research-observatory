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
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal, cast

import yaml
from bs4 import BeautifulSoup, Tag
from build_manifest import windows_path_locks
from jsonschema import Draft202012Validator
from playwright.sync_api import Browser, Page, ViewportSize, sync_playwright
from ui_reference_check import canonical_payload
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
COMMON_REGION_SELECTORS = {
    "application top bar": ("header.topbar",),
    "project home access": ('a.brand[href="index.html"]',),
    "primary-use-case selector": ("[data-workflow-select]",),
    "ordered guided-workflow navigation": ("[data-workflow-nav]",),
    "secondary all-tools inventory": ("[data-all-tools]",),
    "page title and purpose": ("main#main-content .page-header h1", "main#main-content .page-header .page-subtitle"),
    "workflow context with previous/next or return action": ("[data-workflow-context]",),
    "theme toggle": ("[data-theme-toggle]",),
    "trust/provenance footer": ("footer.trust-footer",),
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
APPLICATION_MANIFEST_KEYS = frozenset(
    {"schemaVersion", "documentType", "referenceId", "referencePackageSha256", "sourceFiles", "artifacts"}
)
APPLICATION_EXTERNAL_INPUTS = (
    "Cargo.toml",
    "Cargo.lock",
    "package.json",
    "pnpm-lock.yaml",
    "verification/extensions/desktop-ui.json",
)
APPLICATION_EXCLUDED_DIRECTORIES = frozenset({"dist", "node_modules", "target"})


@dataclass(frozen=True)
class Context:
    repo: Path
    config: dict[str, Any]
    reference: Path
    target: Path
    site: dict[str, Any]
    workflows: dict[str, Any]
    page_contracts: dict[str, dict[str, Any]]
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
            child_directories[:] = sorted(
                name
                for name in child_directories
                if directory_path != root_path or name not in APPLICATION_EXCLUDED_DIRECTORIES
            )
            for name in [*child_directories, *file_names]:
                candidate = directory_path / name
                relative = candidate.relative_to(repo).as_posix()
                confined_path(repo, relative)
            for name in file_names:
                path = directory_path / name
                relative = path.relative_to(repo).as_posix()
                if path.suffix.lower() in UI_SUFFIXES:
                    found.append(relative)
    return sorted(found)


def stable_file_bytes(repo: Path, path: Path) -> bytes:
    relative = path.relative_to(repo).as_posix()
    canonical = confined_path(repo, relative)
    before = canonical.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"application inventory entry is not a regular file: {relative}")
    payload = canonical.read_bytes()
    after = canonical.lstat()
    identity_before = (before.st_dev, before.st_ino, before.st_mode, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_mode, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after or confined_path(repo, relative) != canonical:
        raise ValueError(f"application inventory entry changed while being read: {relative}")
    return payload


def inventory_once(repo: Path, root: Path, *, excluded_directories: frozenset[str] = frozenset()) -> dict[str, str]:
    observed: dict[str, str] = {}
    files: list[Path] = []

    def fail_closed(error: OSError) -> None:
        raise error

    for directory, child_directories, file_names in os.walk(root, followlinks=False, onerror=fail_closed):
        directory_path = Path(directory)
        child_directories[:] = sorted(
            name for name in child_directories if directory_path != root or name not in excluded_directories
        )
        for name in [*child_directories, *sorted(file_names)]:
            candidate = directory_path / name
            relative = candidate.relative_to(repo).as_posix()
            confined_path(repo, relative)
        for name in sorted(file_names):
            candidate = directory_path / name
            files.append(candidate)
    for candidate in sorted(files, key=lambda item: item.relative_to(repo).as_posix()):
        relative = candidate.relative_to(repo).as_posix()
        observed[relative] = hashlib.sha256(stable_file_bytes(repo, candidate)).hexdigest()
    return observed


def file_inventory(
    repo: Path,
    root: Path,
    *,
    excluded_directories: frozenset[str] = frozenset(),
    after_first_pass: Callable[[], None] | None = None,
) -> dict[str, str]:
    first = inventory_once(repo, root, excluded_directories=excluded_directories)
    if after_first_pass is not None:
        after_first_pass()
    second = inventory_once(repo, root, excluded_directories=excluded_directories)
    if first != second:
        raise ValueError(f"application inventory changed while being verified: {root.relative_to(repo).as_posix()}")
    return first


def application_inventory_shape(
    repo: Path, roots: tuple[tuple[Path, frozenset[str]], ...]
) -> tuple[frozenset[Path], frozenset[Path]]:
    files: set[Path] = set()
    directories: set[Path] = set()

    def fail_closed(error: OSError) -> None:
        raise error

    for root, exclusions in roots:
        for directory, child_directories, file_names in os.walk(root, followlinks=False, onerror=fail_closed):
            directory_path = confined_path(repo, Path(directory).relative_to(repo).as_posix())
            child_directories[:] = sorted(
                name for name in child_directories if directory_path != root or name not in exclusions
            )
            directories.add(directory_path)
            for name in [*child_directories, *sorted(file_names)]:
                candidate = confined_path(repo, (directory_path / name).relative_to(repo).as_posix())
                if name in child_directories:
                    directories.add(candidate)
                else:
                    files.add(candidate)
    return frozenset(files), frozenset(directories)


def application_inventory_fingerprints(repo: Path, files: frozenset[Path]) -> dict[str, str]:
    return {
        path.relative_to(repo).as_posix(): hashlib.sha256(stable_file_bytes(repo, path)).hexdigest()
        for path in sorted(files, key=lambda item: item.relative_to(repo).as_posix())
    }


def application_directory_tokens(repo: Path, directories: frozenset[Path]) -> dict[str, tuple[int, int, int, int]]:
    tokens: dict[str, tuple[int, int, int, int]] = {}
    for path in sorted(directories, key=lambda item: item.relative_to(repo).as_posix()):
        metadata = path.lstat()
        if not stat.S_ISDIR(metadata.st_mode):
            raise ValueError(f"application inventory directory changed type: {path.relative_to(repo).as_posix()}")
        tokens[path.relative_to(repo).as_posix()] = (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_mtime_ns,
        )
    return tokens


@contextmanager
def application_inventory_guard(repo: Path, application_root: Path, target: Path) -> Any:
    roots: tuple[tuple[Path, frozenset[str]], ...] = (
        (application_root, APPLICATION_EXCLUDED_DIRECTORIES),
        (target, frozenset()),
    )
    files, directories = application_inventory_shape(repo, roots)
    extra_files = frozenset(confined_path(repo, path) for path in APPLICATION_EXTERNAL_INPUTS)
    with (
        windows_path_locks(list(directories), directories=True),
        windows_path_locks(list(files | extra_files), directories=False),
    ):
        locked_files, locked_directories = application_inventory_shape(repo, roots)
        if (locked_files, locked_directories) != (files, directories):
            raise ValueError("application inventory changed while snapshot locks were acquired")
        fingerprints = application_inventory_fingerprints(repo, files | extra_files)
        directory_tokens = application_directory_tokens(repo, directories)
        yield
        final_files, final_directories = application_inventory_shape(repo, roots)
        if (final_files, final_directories) != (files, directories):
            raise ValueError("application inventory membership changed during verification")
        if application_inventory_fingerprints(repo, files | extra_files) != fingerprints:
            raise ValueError("application inventory content changed during verification")
        if application_directory_tokens(repo, directories) != directory_tokens:
            raise ValueError("application inventory directories changed during verification")


def locked_application_build_errors(repo: Path, config: dict[str, Any], target: Path) -> list[str]:
    errors: list[str] = []
    try:
        application_root = confined_path(repo, str(config["applicationRoot"]))
        manifest_path = confined_path(repo, str(config["applicationManifestPath"]))
        manifest_payload = stable_file_bytes(repo, manifest_path)
        manifest = json.loads(manifest_payload.decode("utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("application-manifest.json must contain a JSON object")
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        return [f"invalid desktop application manifest: {exc}"]
    if set(manifest) != APPLICATION_MANIFEST_KEYS:
        errors.append("desktop application manifest has a noncanonical field set")
        return errors
    if manifest.get("schemaVersion") != "1.0" or manifest.get("documentType") != "desktop-application-build-manifest":
        errors.append("desktop application manifest identity is invalid")
    if manifest.get("referenceId") != config["referenceId"]:
        errors.append("desktop application manifest reference ID is stale")
    if manifest.get("referencePackageSha256") != config["referencePackageSha256"]:
        errors.append("desktop application manifest reference package is stale")

    expected_sources = file_inventory(repo, application_root, excluded_directories=APPLICATION_EXCLUDED_DIRECTORIES)
    for relative in APPLICATION_EXTERNAL_INPUTS:
        source = confined_path(repo, relative)
        expected_sources[relative] = hashlib.sha256(stable_file_bytes(repo, source)).hexdigest()
    if manifest.get("sourceFiles") != dict(sorted(expected_sources.items())):
        errors.append("desktop application manifest does not bind the exact current build-input inventory")

    expected_artifacts = file_inventory(repo, target)
    manifest_relative = manifest_path.relative_to(repo).as_posix()
    expected_artifacts.pop(manifest_relative, None)
    expected_artifacts = {
        Path(relative).relative_to(target.relative_to(repo)).as_posix(): digest
        for relative, digest in expected_artifacts.items()
    }
    if manifest.get("artifacts") != dict(sorted(expected_artifacts.items())):
        errors.append("desktop application manifest does not bind the exact current output inventory")
    final_sources = file_inventory(repo, application_root, excluded_directories=APPLICATION_EXCLUDED_DIRECTORIES)
    for relative in APPLICATION_EXTERNAL_INPUTS:
        source = confined_path(repo, relative)
        final_sources[relative] = hashlib.sha256(stable_file_bytes(repo, source)).hexdigest()
    final_artifacts = file_inventory(repo, target)
    final_artifacts.pop(manifest_relative, None)
    final_artifacts = {
        Path(relative).relative_to(target.relative_to(repo)).as_posix(): digest
        for relative, digest in final_artifacts.items()
    }
    if final_sources != expected_sources:
        errors.append("desktop application build inputs changed during manifest verification")
    if final_artifacts != expected_artifacts:
        errors.append("desktop application outputs changed during manifest verification")
    if stable_file_bytes(repo, manifest_path) != manifest_payload:
        errors.append("desktop application manifest changed during verification")
    return errors


def application_build_errors(repo: Path, config: dict[str, Any], target: Path) -> list[str]:
    try:
        application_root = confined_path(repo, str(config["applicationRoot"]))
        manifest_path = confined_path(repo, str(config["applicationManifestPath"]))
        stable_file_bytes(repo, manifest_path)
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        return [f"invalid desktop application manifest: {exc}"]
    try:
        with application_inventory_guard(repo, application_root, target):
            return locked_application_build_errors(repo, config, target)
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        return [f"invalid desktop application inventory: {exc}"]


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
    found = implementation_files(repo, list(config["implementationRoots"]))
    if config["mode"] == "approved-reference-fixture":
        if found:
            raise ValueError(
                "approved-reference-fixture mode cannot remain active after desktop UI implementation appears: "
                + ", ".join(found)
            )
    elif config["mode"] == "approved-reference-application":
        if not found:
            raise ValueError("approved-reference-application mode requires desktop UI implementation source")
        build_errors = application_build_errors(repo, config, target)
        if build_errors:
            raise ValueError("invalid desktop application build: " + "; ".join(build_errors))
    site = json_object(confined_path(reference, "SITE_MANIFEST.json"))
    workflow_document = json_object(confined_path(reference, "WORKFLOW_CATALOG.json"))
    coverage_document = json_object(confined_path(reference, "CAPABILITY_COVERAGE.json"))
    workflows = workflow_document.get("workflows")
    if not isinstance(workflows, dict):
        raise ValueError("WORKFLOW_CATALOG.json workflows must be an object")
    page_items = site.get("pages")
    if not isinstance(page_items, list):
        raise ValueError("SITE_MANIFEST.json pages must be an array")
    pages = [str(item.get("file")) for item in page_items if isinstance(item, dict)]
    if not pages or len(set(pages)) != len(pages) or any(not page.endswith(".html") for page in pages):
        raise ValueError("approved desktop route inventory must contain unique HTML product pages")
    raw_contracts = coverage_document.get("page_contracts")
    if not isinstance(raw_contracts, dict) or set(raw_contracts) != set(pages):
        raise ValueError("CAPABILITY_COVERAGE.json page contracts must exactly match the product route inventory")
    page_contracts: dict[str, dict[str, Any]] = {}
    for page_name, raw_contract in raw_contracts.items():
        if not isinstance(raw_contract, dict):
            raise ValueError(f"CAPABILITY_COVERAGE.json#{page_name} must be an object")
        raw_regions = raw_contract.get("required_regions")
        if (
            not isinstance(raw_regions, list)
            or not raw_regions
            or any(not isinstance(region, str) or not region.strip() for region in raw_regions)
            or len(raw_regions) != len(set(raw_regions))
        ):
            raise ValueError(f"CAPABILITY_COVERAGE.json#{page_name} required_regions must be unique nonempty strings")
        missing_common = sorted(set(COMMON_REGION_SELECTORS) - set(raw_regions))
        if missing_common:
            raise ValueError(f"CAPABILITY_COVERAGE.json#{page_name} omits common regions {missing_common}")
        page_contracts[page_name] = raw_contract
    return Context(repo, config, reference, target, site, workflows, page_contracts, pages)


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


def semantic_region_contract(document: BeautifulSoup) -> list[dict[str, Any]]:
    """Return UI structure while deliberately excluding illustrative prose/data."""
    contract: list[dict[str, Any]] = []
    semantic_text_tags = {"button", "dt", "h2", "h3", "h4", "h5", "h6", "label", "legend", "summary", "th"}
    for element in document.select("body *"):
        if (
            not isinstance(element, Tag)
            or element.find_parent("svg") is not None
            or element.name in {"script", "style"}
        ):
            continue
        attributes: dict[str, Any] = {}
        for name, raw_value in sorted(element.attrs.items()):
            if name == "style" or not (name in {"class", "href", "id", "role", "type"} or name.startswith("data-")):
                continue
            value = sorted(str(item) for item in raw_value) if isinstance(raw_value, list) else str(raw_value)
            attributes[name] = value
        item: dict[str, Any] = {"tag": element.name, "attributes": attributes}
        if element.name in semantic_text_tags:
            item["semanticText"] = " ".join(element.get_text(" ", strip=True).split())
        contract.append(item)
    return contract


def check_routes(context: Context) -> dict[str, Any]:
    errors: list[str] = []
    page_ids: set[str] = set()
    linked_routes: set[str] = set()
    region_count = 0
    for page_name in context.pages:
        reference_page = soup(confined_path(context.reference, page_name))
        target_page = soup(confined_path(context.target, page_name))
        required_regions = cast(list[str], context.page_contracts[page_name]["required_regions"])
        region_count += len(required_regions)
        expected_id = str(reference_page.body.get("data-page", "")) if reference_page.body else ""
        observed_id = str(target_page.body.get("data-page", "")) if target_page.body else ""
        if not observed_id or observed_id != expected_id or observed_id in page_ids:
            errors.append(
                f"{source(context, 'routes')}#{page_name}: route identity must be unique and match {expected_id!r}"
            )
        page_ids.add(observed_id)
        for region, selectors in COMMON_REGION_SELECTORS.items():
            for selector in selectors:
                if target_page.select_one(selector) is None:
                    errors.append(
                        f"{source(context, 'pages')}#{page_name}: required region {region!r} "
                        f"does not satisfy {selector}"
                    )
        if semantic_region_contract(target_page) != semantic_region_contract(reference_page):
            errors.append(
                f"{source(context, 'pages')}#{page_name}: executable region structure differs for exact "
                f"required_regions={required_regions}"
            )
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
        {
            "routes": len(context.pages),
            "uniqueRouteIds": len(page_ids),
            "requiredRegionContracts": region_count,
            "commonRequiredRegions": sorted(COMMON_REGION_SELECTORS),
        },
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


def keyboard_link_errors(
    page: Page,
    selector: str,
    expected: list[str],
    label: str,
) -> tuple[list[str], int]:
    errors: list[str] = []
    page.evaluate(
        """({selector}) => {
          document.querySelector('[data-conformance-sentinel]')?.remove();
          const container = document.querySelector(selector);
          if (!container) return;
          const sentinel = document.createElement('button');
          sentinel.type = 'button';
          sentinel.dataset.conformanceSentinel = 'true';
          sentinel.style.cssText = 'position:fixed;left:0;top:0;width:1px;height:1px;opacity:.01';
          container.before(sentinel);
          window.__conformanceActivation = null;
          container.querySelectorAll('a[href]').forEach(link => link.addEventListener('click', event => {
            event.preventDefault();
            window.__conformanceActivation = link.getAttribute('href');
          }));
        }""",
        {"selector": selector},
    )
    sentinel = page.locator("[data-conformance-sentinel]")
    if sentinel.count() != 1:
        return [f"{label}: keyboard navigation container is absent"], 0
    sentinel.focus()
    for index, expected_href in enumerate(expected):
        page.keyboard.press("Tab")
        observed = page.evaluate(
            """() => document.activeElement?.tagName === 'A'
              ? document.activeElement.getAttribute('href') : null"""
        )
        if observed != expected_href:
            errors.append(
                f"{label}: keyboard focus order differs at {index}; expected {expected_href!r}, found {observed!r}"
            )
            continue
        page.keyboard.press("Enter")
        activated = page.evaluate("window.__conformanceActivation")
        if activated != expected_href:
            errors.append(
                f"{label}: keyboard activation failed at {index}; expected {expected_href!r}, found {activated!r}"
            )
    sentinel.evaluate("node => node.remove()")
    return errors, len(expected)


def check_workflows(context: Context) -> dict[str, Any]:
    errors: list[str] = []
    if len(context.workflows) != 14:
        errors.append(f"{source(context, 'workflows')}: expected exactly 14 workflow profiles")
    playwright, browser = open_browser(context)
    cases = 0
    keyboard_cases = 0
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
                keyboard_errors, checked = keyboard_link_errors(
                    page,
                    "[data-workflow-nav]",
                    [str(step) for step in steps],
                    f"{source(context, 'workflows')}#{workflow_id}",
                )
                errors.extend(keyboard_errors)
                keyboard_cases += checked
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
                    keyboard_errors, checked = keyboard_link_errors(
                        page,
                        "[data-workflow-context]",
                        expected,
                        f"{source(context, 'workflows')}#{workflow_id}:{steps[index]}",
                    )
                    errors.extend(keyboard_errors)
                    keyboard_cases += checked
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
        {
            "profiles": len(context.workflows),
            "browserCases": cases,
            "keyboardCases": keyboard_cases,
            "approvedRepeatedRoutes": repeated_routes,
        },
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
    responsive_visual_cases = 0
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
                    reference_page.evaluate("document.fonts.ready")
                    measurements = page.evaluate(
                        """() => { const root=document.documentElement; return {
                          scrollWidth:root.scrollWidth, clientWidth:root.clientWidth,
                          scrollHeight:root.scrollHeight, clientHeight:root.clientHeight}; }"""
                    )
                    expected_measurements = reference_page.evaluate(
                        """() => { const root=document.documentElement; return {
                          scrollWidth:root.scrollWidth, clientWidth:root.clientWidth,
                          scrollHeight:root.scrollHeight, clientHeight:root.clientHeight}; }"""
                    )
                    if measurements != expected_measurements:
                        errors.append(
                            f"{source(context, 'style')}#{page_name}: responsive geometry differs from reference "
                            f"at {viewport['label']}"
                        )
                    screenshot_options: dict[str, Any] = {
                        "full_page": False,
                        "animations": "disabled",
                        "caret": "hide",
                        "scale": "device",
                    }
                    observed_image = page.screenshot(**screenshot_options)
                    expected_image = reference_page.screenshot(**screenshot_options)
                    if hashlib.sha256(observed_image).digest() != hashlib.sha256(expected_image).digest():
                        errors.append(
                            f"{source(context, 'style')}#{page_name}: responsive visual contract differs from "
                            f"reference at {viewport['label']}"
                        )
                    responsive_cases += 1
                    responsive_visual_cases += 1
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
            "responsiveVisualCases": responsive_visual_cases,
            "standard": "approved-reference accessibility and responsive contract",
        },
    )


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=False, timeout=30)
    if completed.returncode != 0:
        raise ValueError(completed.stderr.strip() or f"git {' '.join(args)} failed")
    return completed.stdout.strip()


def schema_errors(value: object, schema: dict[str, Any], label: str) -> list[str]:
    issues = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda issue: list(issue.absolute_path))
    return [
        f"{label}: {'.'.join(str(part) for part in issue.absolute_path) or '<root>'}: {issue.message}"
        for issue in issues
    ]


def baseline_document_errors(
    value: dict[str, Any],
    label: str,
    schema: dict[str, Any],
    expected_pages: list[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    errors.extend(schema_errors(value, schema, label))
    if errors:
        return errors
    settings = cast(dict[str, Any], value["settings"])
    for field in ("platform", "playwrightVersion", "browserVersion"):
        if value[field] != settings[field]:
            errors.append(f"{label}: top-level {field} must equal settings.{field}")
    entries = value.get("entries")
    assert isinstance(entries, dict)
    viewport = cast(dict[str, int], settings["viewport"])
    observed_pages: dict[str, set[str]] = {}
    for key, raw_entry in cast(dict[str, dict[str, Any]], entries).items():
        entry_label = f"{label}#{key}"
        page_name = cast(str, raw_entry["page"])
        theme = cast(str, raw_entry["theme"])
        if key != f"{page_name}::{theme}":
            errors.append(f"{entry_label}: visual entry key, page, and theme are inconsistent")
        if raw_entry["width"] != viewport["width"] or raw_entry["height"] != viewport["height"]:
            errors.append(f"{entry_label}: visual dimensions must equal the governed viewport")
        observed_pages.setdefault(page_name, set()).add(theme)
    incomplete = sorted(page_name for page_name, themes in observed_pages.items() if themes != {"light", "dark"})
    if incomplete:
        errors.append(f"{label}: every page requires exact light/dark entries; incomplete={incomplete}")
    if expected_pages is not None and set(observed_pages) != set(expected_pages):
        errors.append(
            f"{label}: entry pages must exactly match product routes; "
            f"missing={sorted(set(expected_pages) - set(observed_pages))}, "
            f"extra={sorted(set(observed_pages) - set(expected_pages))}"
        )
    return errors


def git_blob_at(repo: Path, revision: str, relative: str) -> tuple[bytes | None, str | None]:
    listing = subprocess.run(
        ["git", "ls-tree", revision, "--", relative],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if listing.returncode != 0:
        return None, f"cannot inspect {revision}:{relative}"
    if not listing.stdout.strip():
        return None, None
    metadata, separator, path = listing.stdout.strip().partition("\t")
    fields = metadata.split()
    if (
        not separator
        or path != relative
        or len(fields) != 3
        or fields[0] not in {"100644", "100755"}
        or fields[1] != "blob"
    ):
        return None, f"{revision}:{relative} must be a regular Git blob"
    completed = subprocess.run(
        ["git", "show", f"{revision}:{relative}"],
        cwd=repo,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if completed.returncode != 0:
        return None, f"cannot read {revision}:{relative}"
    return completed.stdout, None


def git_json_at(repo: Path, revision: str, relative: str) -> tuple[dict[str, Any] | None, bytes | None, str | None]:
    payload, read_error = git_blob_at(repo, revision, relative)
    if read_error or payload is None:
        return None, payload, read_error
    try:
        loaded = json.loads(payload.decode("utf-8"))
    except UnicodeDecodeError:
        return None, payload, f"{revision}:{relative}: invalid UTF-8"
    except json.JSONDecodeError as exc:
        return None, payload, f"{revision}:{relative}: invalid JSON: {exc.msg}"
    if not isinstance(loaded, dict):
        return None, payload, f"{revision}:{relative}: baseline must be an object"
    return loaded, payload, None


LEGACY_APPROVAL_KEYS = frozenset(
    {
        "reference_id",
        "version",
        "status",
        "approved_by",
        "approved_at",
        "approval_basis",
        "supersedes",
        "scope",
        "implementation_rule",
        "deferred_surfaces",
    }
)
AUTHORITY_APPROVAL_KEYS = LEGACY_APPROVAL_KEYS | {"approval_kind", "authority"}
APPROVAL_AUTHORITY_KEYS = frozenset(
    {
        "amendment_id",
        "change_request_id",
        "approval_record",
        "approval_record_sha256",
        "approval_record_introduction_commit",
    }
)
WAVE_SLICE_APPROVAL_AUTHORITY_KEYS = frozenset(
    {
        "wave_id",
        "slice_id",
        "approved_wave_commit",
        "proposal_commit",
        "slice_plan",
    }
)
REFERENCE_MANIFEST_KEYS = frozenset(
    {
        "reference_id",
        "version",
        "status",
        "approval_file",
        "canonical_token_file",
        "style_guides",
        "workflow_catalog",
        "page_contracts",
        "page_inventory",
        "site_manifest",
        "generator",
        "validator",
        "governed_files",
        "file_hashes",
    }
)


def approval_record_errors(value: object, label: str, reference_id: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{label}: approval record must be an object"]
    errors: list[str] = []
    keys = set(value)
    if keys not in {LEGACY_APPROVAL_KEYS, AUTHORITY_APPROVAL_KEYS}:
        expected = AUTHORITY_APPROVAL_KEYS if keys & {"approval_kind", "authority"} else LEGACY_APPROVAL_KEYS
        errors.append(
            f"{label}: approval fields must be exact; missing={sorted(expected - keys)}, "
            f"extra={sorted(keys - expected)}"
        )
        return errors
    if value["reference_id"] != reference_id or value["status"] != "approved":
        errors.append(f"{label}: approval identity/status does not match the baseline")
    for field in ("version", "approved_by", "approval_basis", "implementation_rule"):
        if not isinstance(value[field], str) or not value[field].strip():
            errors.append(f"{label}: {field} must be a nonempty string")
    try:
        if not isinstance(value["approved_at"], str):
            raise ValueError
        approved_at = value["approved_at"]
        if "T" in approved_at:
            datetime.fromisoformat(approved_at)
        else:
            date.fromisoformat(approved_at)
    except ValueError:
        errors.append(f"{label}: approved_at must be a valid ISO date")
    if value["supersedes"] is not None and (not isinstance(value["supersedes"], str) or not value["supersedes"]):
        errors.append(f"{label}: supersedes must be null or a nonempty reference ID")
    scope = value["scope"]
    if not isinstance(scope, dict) or set(scope) != {"normative", "illustrative"}:
        errors.append(f"{label}: scope must contain exact normative and illustrative arrays")
    else:
        for field in ("normative", "illustrative"):
            items = scope[field]
            if (
                not isinstance(items, list)
                or not items
                or any(not isinstance(item, str) or not item.strip() for item in items)
                or len(items) != len(set(items))
            ):
                errors.append(f"{label}: scope.{field} must be unique nonempty strings")
    deferred = value["deferred_surfaces"]
    if not isinstance(deferred, list) or any(not isinstance(item, str) or not item.strip() for item in deferred):
        errors.append(f"{label}: deferred_surfaces must be an array of nonempty strings")
    if keys == AUTHORITY_APPROVAL_KEYS:
        authority = value["authority"]
        if value["approval_kind"] != "human" or not re.fullmatch(
            r"human:[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", str(value["approved_by"])
        ):
            errors.append(f"{label}: authority-bound approval must identify an explicit human approver")
        if not isinstance(authority, dict):
            errors.append(f"{label}: authority must be an object")
        elif set(authority) == APPROVAL_AUTHORITY_KEYS:
            if (
                not re.fullmatch(r"W[0-9]+\.A[0-9]{2}", str(authority["amendment_id"]))
                or not re.fullmatch(r"ECR-[0-9]{4}", str(authority["change_request_id"]))
                or authority["approval_record"] != f"planning/wave-amendment-approvals/{authority['amendment_id']}.json"
                or not re.fullmatch(r"[0-9a-f]{64}", str(authority["approval_record_sha256"]))
                or not re.fullmatch(r"[0-9a-f]{40}", str(authority["approval_record_introduction_commit"]))
            ):
                errors.append(f"{label}: authority-bound approval fields are malformed or inconsistent")
        elif set(authority) == WAVE_SLICE_APPROVAL_AUTHORITY_KEYS:
            slice_id = str(authority["slice_id"])
            capability_id = slice_id.split(".", 1)[0]
            if (
                not re.fullmatch(r"W[0-9]+", str(authority["wave_id"]))
                or not re.fullmatch(r"CAP-[0-9]+\.S[0-9]+", slice_id)
                or not re.fullmatch(r"[0-9a-f]{40}", str(authority["approved_wave_commit"]))
                or not re.fullmatch(r"[0-9a-f]{40}", str(authority["proposal_commit"]))
                or not str(authority["slice_plan"]).startswith(f"planning/slice-plans/{capability_id}/{slice_id}-")
                or not str(authority["slice_plan"]).endswith(".md")
            ):
                errors.append(f"{label}: wave/slice authority fields are malformed or inconsistent")
        else:
            errors.append(f"{label}: authority must contain one exact supported authority field set")
    return errors


def commit_is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repo,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if completed.returncode not in {0, 1}:
        raise ValueError(completed.stderr.decode("utf-8", errors="replace").strip() or "git merge-base failed")
    return completed.returncode == 0


def amendment_authority_bound_approval_errors(
    repo: Path,
    approval: dict[str, Any],
    approval_commit: str,
    approval_path: str,
) -> list[str]:
    authority = approval.get("authority")
    if approval.get("approval_kind") != "human" or not isinstance(authority, dict):
        return []
    label = f"{approval_commit}:{approval_path}"
    errors: list[str] = []
    authority_path = str(authority.get("approval_record", ""))
    introduction = str(authority.get("approval_record_introduction_commit", ""))
    amendment_id = str(authority.get("amendment_id", ""))
    change_request_id = str(authority.get("change_request_id", ""))
    try:
        resolved_introduction = git(repo, "rev-parse", "--verify", f"{introduction}^{{commit}}")
    except ValueError:
        return [f"{label}: authority approval-record introduction commit cannot be resolved"]
    if resolved_introduction != introduction:
        return [f"{label}: authority approval-record introduction must use an exact full commit SHA"]
    if introduction == approval_commit or not commit_is_ancestor(repo, introduction, approval_commit):
        errors.append(f"{label}: authority approval record must strictly precede the reference approval")

    changed = git(
        repo,
        "diff-tree",
        "--root",
        "--no-commit-id",
        "--name-only",
        "-r",
        introduction,
    ).splitlines()
    if authority_path not in changed:
        return [*errors, f"{label}: authority introduction commit did not change the cited approval record"]
    authority_payload, authority_error = git_blob_at(repo, introduction, authority_path)
    if authority_error or authority_payload is None:
        return [*errors, authority_error or f"{label}: authority approval record is absent"]
    parent_payload, parent_error = git_blob_at(repo, f"{introduction}^", authority_path)
    if parent_error is None and parent_payload is not None:
        errors.append(f"{label}: cited authority commit is not the approval record introduction")
    if hashlib.sha256(authority_payload).hexdigest() != authority.get("approval_record_sha256"):
        errors.append(f"{label}: authority approval-record hash differs from its introduction bytes")
    approval_authority_payload, approval_authority_error = git_blob_at(repo, approval_commit, authority_path)
    if approval_authority_error or approval_authority_payload != authority_payload:
        errors.append(f"{label}: authority approval record changed or disappeared before reference approval")

    try:
        authority_record = json.loads(authority_payload.decode("utf-8"))
    except UnicodeDecodeError, json.JSONDecodeError:
        return [*errors, f"{label}: authority approval record is not valid UTF-8 JSON"]
    if not isinstance(authority_record, dict):
        return [*errors, f"{label}: authority approval record must be an object"]
    expected_human = f"human:{authority_record.get('approvedBy', '')}"
    authorized_tasks = authority_record.get("authorizedTaskIds")
    if (
        authority_record.get("schemaVersion") != "1.0"
        or authority_record.get("documentType") != "wave-amendment-approval"
        or authority_record.get("amendmentId") != amendment_id
        or authority_record.get("changeRequestId") != change_request_id
        or authority_record.get("targetWave") != amendment_id.split(".", 1)[0]
        or authority_record.get("status") != "APPROVED"
        or not isinstance(authority_record.get("approvedBy"), str)
        or not authority_record["approvedBy"].strip()
        or approval.get("approved_by") != expected_human
        or approval.get("approved_at") != authority_record.get("approvedAt")
        or not isinstance(authorized_tasks, list)
        or not authorized_tasks
        or any(not isinstance(item, str) or not item.startswith(f"{amendment_id}.T") for item in authorized_tasks)
    ):
        errors.append(f"{label}: authority approval status, identity, approver, time, or authorized tasks are invalid")

    packet = authority_record.get("packet")
    packet_commit = str(packet.get("commit", "")) if isinstance(packet, dict) else ""
    packet_path = str(packet.get("path", "")) if isinstance(packet, dict) else ""
    packet_sha256 = str(packet.get("sha256", "")) if isinstance(packet, dict) else ""
    expected_packet_path = f"planning/enabler-change-requests/{change_request_id}.packet.json"
    try:
        resolved_packet = git(repo, "rev-parse", "--verify", f"{packet_commit}^{{commit}}")
    except ValueError:
        resolved_packet = ""
    if (
        not re.fullmatch(r"[0-9a-f]{40}", packet_commit)
        or resolved_packet != packet_commit
        or packet_path != expected_packet_path
        or not commit_is_ancestor(repo, packet_commit, introduction)
    ):
        errors.append(f"{label}: authority packet identity or ancestry is invalid")
    else:
        packet_payload, packet_error = git_blob_at(repo, packet_commit, packet_path)
        if packet_error or packet_payload is None or hashlib.sha256(packet_payload).hexdigest() != packet_sha256:
            errors.append(f"{label}: authority packet bytes do not match the approved record")
        else:
            try:
                packet_record = json.loads(packet_payload.decode("utf-8"))
            except UnicodeDecodeError, json.JSONDecodeError:
                packet_record = None
            if not isinstance(packet_record, dict) or (
                packet_record.get("documentType") != "enabler-change-request-packet"
                or packet_record.get("changeRequestId") != change_request_id
                or packet_record.get("proposedAmendmentId") != amendment_id
                or packet_record.get("targetWave") != amendment_id.split(".", 1)[0]
                or packet_record.get("status") != "pending-approval"
                or packet_record.get("executionState") != "non-executable"
            ):
                errors.append(f"{label}: authority packet does not bind the cited amendment and change request")

    prior_approval_commits = git(
        repo,
        "log",
        "--full-history",
        "--format=%H",
        f"{approval_commit}^",
        "--",
        approval_path,
    ).splitlines()
    if prior_approval_commits and (
        prior_approval_commits[0] == introduction
        or not commit_is_ancestor(repo, prior_approval_commits[0], introduction)
    ):
        errors.append(f"{label}: authority must be introduced after the prior reference approval")
    for prior_commit in prior_approval_commits:
        prior_payload, prior_error = git_blob_at(repo, prior_commit, approval_path)
        if prior_error or prior_payload is None:
            continue
        try:
            prior_approval = yaml.safe_load(prior_payload.decode("utf-8"))
        except UnicodeDecodeError, yaml.YAMLError:
            continue
        prior_authority = prior_approval.get("authority") if isinstance(prior_approval, dict) else None
        if isinstance(prior_authority, dict) and (
            prior_authority.get("approval_record") == authority_path
            or prior_authority.get("approval_record_introduction_commit") == introduction
        ):
            errors.append(f"{label}: authority was already consumed by a prior reference approval")
            break
    return errors


def wave_slice_authority_bound_approval_errors(
    repo: Path,
    approval: dict[str, Any],
    approval_commit: str,
    approval_path: str,
) -> list[str]:
    authority = approval.get("authority")
    if not isinstance(authority, dict) or set(authority) != WAVE_SLICE_APPROVAL_AUTHORITY_KEYS:
        return []
    label = f"{approval_commit}:{approval_path}"
    errors: list[str] = []
    wave_id = str(authority["wave_id"])
    slice_id = str(authority["slice_id"])
    approved_wave_commit = str(authority["approved_wave_commit"])
    proposal_commit = str(authority["proposal_commit"])
    slice_plan = str(authority["slice_plan"])

    resolved: dict[str, str] = {}
    for field, commit in (("approved Wave", approved_wave_commit), ("proposal", proposal_commit)):
        try:
            resolved[field] = git(repo, "rev-parse", "--verify", f"{commit}^{{commit}}")
        except ValueError:
            errors.append(f"{label}: {field} authority commit cannot be resolved")
    if errors:
        return errors
    if resolved["approved Wave"] != approved_wave_commit or resolved["proposal"] != proposal_commit:
        return [f"{label}: wave/slice authority must use exact full commit SHAs"]
    if not commit_is_ancestor(repo, approved_wave_commit, proposal_commit):
        errors.append(f"{label}: approved Wave packet must precede the reference proposal")
    approval_parents = git(repo, "rev-list", "--parents", "-n", "1", approval_commit).split()[1:]
    if approval_parents != [proposal_commit]:
        errors.append(f"{label}: reference approval must be the direct child of its exact proposal")

    proposal_changed = set(
        git(
            repo,
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-only",
            "-r",
            proposal_commit,
        ).splitlines()
    )
    approval_changed = set(
        git(
            repo,
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-only",
            "-r",
            approval_commit,
        ).splitlines()
    )
    manifest_path = "design/ui-reference/REFERENCE_MANIFEST.yaml"
    expected_handoff_paths = {approval_path, manifest_path}
    if approval_path not in proposal_changed:
        errors.append(f"{label}: exact proposal commit did not change the approval record")
    if approval_changed != expected_handoff_paths:
        errors.append(f"{label}: approval materialization must change only approval and manifest governance files")

    proposal_payload, proposal_error = git_blob_at(repo, proposal_commit, approval_path)
    proposal_manifest_payload, proposal_manifest_error = git_blob_at(repo, proposal_commit, manifest_path)
    if proposal_error or proposal_payload is None or proposal_manifest_error or proposal_manifest_payload is None:
        return [*errors, f"{label}: exact proposal governance package is unavailable"]
    try:
        proposal = yaml.safe_load(proposal_payload.decode("utf-8"))
        proposal_manifest = yaml.safe_load(proposal_manifest_payload.decode("utf-8"))
    except UnicodeDecodeError, yaml.YAMLError:
        return [*errors, f"{label}: exact proposal governance package is unreadable"]
    proposal_authority = proposal.get("authority") if isinstance(proposal, dict) else None
    expected_proposal_authority = {key: value for key, value in authority.items() if key != "proposal_commit"}
    stable_fields = {
        "reference_id",
        "version",
        "supersedes",
        "scope",
        "implementation_rule",
        "deferred_surfaces",
    }
    if (
        not isinstance(proposal, dict)
        or set(proposal) != AUTHORITY_APPROVAL_KEYS
        or proposal.get("status") != "proposed"
        or proposal.get("approval_kind") != "pending-human"
        or proposal.get("approved_by") is not None
        or proposal.get("approved_at") is not None
        or not isinstance(proposal.get("approval_basis"), str)
        or not proposal["approval_basis"].strip()
        or proposal_authority != expected_proposal_authority
        or any(proposal.get(field) != approval.get(field) for field in stable_fields)
    ):
        errors.append(f"{label}: approved reference does not exactly materialize its cited proposal")
    if (
        not isinstance(proposal_manifest, dict)
        or proposal_manifest.get("reference_id") != approval.get("reference_id")
        or proposal_manifest.get("version") != approval.get("version")
        or proposal_manifest.get("status") != "proposed"
        or (proposal_manifest.get("file_hashes") or {}).get("APPROVAL.yaml")
        != hashlib.sha256(canonical_payload("APPROVAL.yaml", proposal_payload)).hexdigest()
    ):
        errors.append(f"{label}: proposal manifest does not bind the exact proposed approval bytes")

    backlog_payload, backlog_error = git_blob_at(repo, proposal_commit, "planning/backlog.yaml")
    slice_payload, slice_error = git_blob_at(repo, proposal_commit, slice_plan)
    if backlog_error or backlog_payload is None or slice_error or slice_payload is None:
        return [*errors, f"{label}: Wave or slice authority source is unavailable at the proposal"]
    try:
        backlog = yaml.safe_load(backlog_payload.decode("utf-8"))
        slice_text = slice_payload.decode("utf-8")
        slice_parts = slice_text.split("---", 2)
        slice_meta = yaml.safe_load(slice_parts[1]) if len(slice_parts) == 3 else None
    except UnicodeDecodeError, yaml.YAMLError:
        return [*errors, f"{label}: Wave or slice authority source is unreadable"]
    waves = backlog.get("waves") if isinstance(backlog, dict) else None
    wave = next(
        (item for item in waves or [] if isinstance(item, dict) and item.get("id") == wave_id),
        None,
    )
    wave_approval = wave.get("approval") if isinstance(wave, dict) else None
    slice_approval = slice_meta.get("approval") if isinstance(slice_meta, dict) else None
    if (
        not isinstance(wave_approval, dict)
        or wave_approval.get("status") != "APPROVED"
        or wave_approval.get("approved_commit") != approved_wave_commit
        or slice_id not in (wave_approval.get("slice_ids") or [])
        or not isinstance(slice_meta, dict)
        or slice_meta.get("slice_id") != slice_id
        or slice_meta.get("capability_id") != slice_id.split(".", 1)[0]
        or slice_meta.get("wave") != wave_id
        or slice_meta.get("status") != "approved"
        or not isinstance(slice_approval, dict)
        or slice_approval.get("status") != "approved"
        or slice_approval.get("approved_commit") != approved_wave_commit
    ):
        errors.append(f"{label}: Wave packet and slice-plan approval authority do not match")

    prior_approval_commits = git(
        repo,
        "log",
        "--full-history",
        "--format=%H",
        f"{approval_commit}^",
        "--",
        approval_path,
    ).splitlines()
    for prior_commit in prior_approval_commits:
        prior_payload, prior_error = git_blob_at(repo, prior_commit, approval_path)
        if prior_error or prior_payload is None:
            continue
        try:
            prior_approval = yaml.safe_load(prior_payload.decode("utf-8"))
        except UnicodeDecodeError, yaml.YAMLError:
            continue
        prior_authority = prior_approval.get("authority") if isinstance(prior_approval, dict) else None
        if isinstance(prior_authority, dict) and prior_authority.get("proposal_commit") == proposal_commit:
            errors.append(f"{label}: proposal authority was already consumed by a prior reference approval")
            break
    return errors


def authority_bound_approval_errors(
    repo: Path,
    approval: dict[str, Any],
    approval_commit: str,
    approval_path: str,
) -> list[str]:
    authority = approval.get("authority")
    if not isinstance(authority, dict):
        return []
    if set(authority) == APPROVAL_AUTHORITY_KEYS:
        return amendment_authority_bound_approval_errors(repo, approval, approval_commit, approval_path)
    if set(authority) == WAVE_SLICE_APPROVAL_AUTHORITY_KEYS:
        return wave_slice_authority_bound_approval_errors(repo, approval, approval_commit, approval_path)
    return []


def reference_package_at(
    repo: Path,
    revision: str,
    reference_id: str,
) -> tuple[bytes | None, str | None, list[str]]:
    errors: list[str] = []
    approval_path = "design/ui-reference/APPROVAL.yaml"
    manifest_path = "design/ui-reference/REFERENCE_MANIFEST.yaml"
    approval_bytes, approval_error = git_blob_at(repo, revision, approval_path)
    manifest_bytes, manifest_error = git_blob_at(repo, revision, manifest_path)
    errors.extend(error for error in (approval_error, manifest_error) if error)
    if errors or approval_bytes is None or manifest_bytes is None:
        return approval_bytes, None, errors
    try:
        approval = yaml.safe_load(approval_bytes.decode("utf-8"))
        manifest = yaml.safe_load(manifest_bytes.decode("utf-8"))
    except UnicodeDecodeError, yaml.YAMLError:
        return approval_bytes, None, [*errors, f"{revision}: approved reference governance records are unreadable"]
    errors.extend(approval_record_errors(approval, f"{revision}:{approval_path}", reference_id))
    if isinstance(approval, dict) and approval.get("approval_kind") == "human":
        approval_commit = git(repo, "log", "-1", "--format=%H", revision, "--", approval_path)
        if not approval_commit:
            errors.append(f"{revision}:{approval_path}: approval introduction commit cannot be found")
        else:
            errors.extend(authority_bound_approval_errors(repo, approval, approval_commit, approval_path))
    if not isinstance(manifest, dict) or set(manifest) != REFERENCE_MANIFEST_KEYS:
        errors.append(f"{revision}:{manifest_path}: manifest fields must be exact")
        return approval_bytes, None, errors
    if (
        manifest["reference_id"] != reference_id
        or manifest["status"] != "approved"
        or manifest["approval_file"] != "APPROVAL.yaml"
        or not isinstance(approval, dict)
        or manifest["version"] != approval.get("version")
    ):
        errors.append(f"{revision}:{manifest_path}: manifest identity/status/version is inconsistent")
    governed = manifest["governed_files"]
    declared_hashes = manifest["file_hashes"]
    if (
        not isinstance(governed, list)
        or not governed
        or any(not isinstance(item, str) or not item for item in governed)
        or len(governed) != len(set(governed))
        or not isinstance(declared_hashes, dict)
        or set(declared_hashes) != set(governed)
    ):
        errors.append(f"{revision}:{manifest_path}: governed file/hash inventory is invalid")
        return approval_bytes, None, errors
    observed: dict[str, str] = {}
    for relative in governed:
        payload, read_error = git_blob_at(repo, revision, f"design/ui-reference/{relative}")
        if read_error or payload is None:
            errors.append(read_error or f"{revision}: missing governed reference file {relative}")
            continue
        digest = hashlib.sha256(canonical_payload(relative, payload)).hexdigest()
        observed[relative] = digest
        if declared_hashes.get(relative) != digest:
            errors.append(f"{revision}:{manifest_path}: governed hash differs for {relative}")
    package_sha256 = hashlib.sha256(
        json.dumps(observed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return approval_bytes, package_sha256, errors


def reference_package_errors(
    repo: Path,
    baseline: dict[str, Any],
    baseline_commit: str,
    approval_commit: str,
    *,
    require_package_at_approval: bool = True,
) -> list[str]:
    reference_id = str(baseline.get("referenceId", ""))
    expected_package = str(baseline.get("referencePackageSha256", ""))
    approval_bytes, approved_package, approval_errors = reference_package_at(repo, approval_commit, reference_id)
    active_approval_payload, active_approval_error = git_blob_at(
        repo, baseline_commit, "design/ui-reference/APPROVAL.yaml"
    )
    active_reference_id = ""
    active_parse_errors: list[str] = []
    if active_approval_error or active_approval_payload is None:
        active_parse_errors.append(active_approval_error or f"{baseline_commit}: approved reference record is absent")
    else:
        try:
            active_approval = yaml.safe_load(active_approval_payload.decode("utf-8"))
            if not isinstance(active_approval, dict) or not isinstance(active_approval.get("reference_id"), str):
                raise ValueError
            active_reference_id = str(active_approval["reference_id"])
        except UnicodeDecodeError, ValueError, yaml.YAMLError:
            active_parse_errors.append(f"{baseline_commit}: approved reference record is unreadable")
    current_approval_bytes, baseline_package, baseline_errors = reference_package_at(
        repo, baseline_commit, active_reference_id or reference_id
    )
    errors = [*approval_errors, *active_parse_errors, *baseline_errors]
    if require_package_at_approval and approved_package is not None and approved_package != expected_package:
        errors.append(f"{baseline_commit}: baseline-bound reference package did not exist at the cited approval commit")
    if active_reference_id == reference_id:
        if (
            approval_bytes is not None
            and current_approval_bytes is not None
            and approval_bytes != current_approval_bytes
        ):
            errors.append(f"{baseline_commit}: approved reference record differs from the cited approval commit")
        if baseline_package is not None and baseline_package != expected_package:
            errors.append(f"{baseline_commit}: visual baseline does not bind the exact approved reference package")
        if (
            require_package_at_approval
            and approved_package is not None
            and baseline_package is not None
            and approved_package != baseline_package
        ):
            errors.append(f"{baseline_commit}: approved reference package changed after its cited approval commit")
    elif active_reference_id:
        transition_commit = git(
            repo,
            "log",
            "-1",
            "--format=%H",
            baseline_commit,
            "--",
            "design/ui-reference/APPROVAL.yaml",
        )
        transition_approval, transition_package, transition_errors = reference_package_at(
            repo, transition_commit, active_reference_id
        )
        errors.extend(transition_errors)
        if (
            transition_approval is None
            or current_approval_bytes != transition_approval
            or transition_package is None
            or baseline_package != transition_package
        ):
            errors.append(f"{baseline_commit}: newer approved reference package changed after its approval commit")
    return errors


def approval_lineage_errors(
    repo: Path,
    baseline: dict[str, Any],
    baseline_commit: str,
    package_cache: dict[tuple[str, str, str, bool], list[str]] | None = None,
    *,
    verify_package_at_original_approval: bool = True,
) -> list[str]:
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
        tree = git(repo, "rev-parse", f"{baseline_commit}:design/ui-reference")
    except ValueError:
        return [*errors, f"{baseline_commit}: approved reference tree is absent"]
    cache_key = (
        approval_commit,
        str(baseline.get("referencePackageSha256", "")),
        tree,
        verify_package_at_original_approval,
    )
    if package_cache is not None and cache_key in package_cache:
        errors.extend(package_cache[cache_key])
    else:
        package_errors = reference_package_errors(
            repo,
            baseline,
            baseline_commit,
            approval_commit,
            require_package_at_approval=verify_package_at_original_approval,
        )
        errors.extend(package_errors)
        if package_cache is not None:
            package_cache[cache_key] = package_errors
    return errors


def font_face_available(page: Page, font: str) -> bool:
    return bool(
        page.evaluate(
            """font => {
              const canvas = document.createElement('canvas');
              const context = canvas.getContext('2d');
              if (!context) return false;
              const sample = 'mmmmmmmmmmlliWW00@# Research Observatory';
              const metrics = family => {
                context.font = `72px ${family}`;
                const value = context.measureText(sample);
                return [value.width, value.actualBoundingBoxAscent, value.actualBoundingBoxDescent];
              };
              const same = (left, right) => left.every((value, index) => Math.abs(value - right[index]) < 0.01);
              const escaped = String(font).replace(/["\\\\]/g, '\\$&');
              return ['monospace', 'serif', 'sans-serif'].some(fallback =>
                !same(metrics(`"${escaped}", ${fallback}`), metrics(fallback))
              );
            }""",
            font,
        )
    )


def render_visuals(context: Context, cases: set[tuple[str, str]] | None = None) -> tuple[dict[str, Any], list[str]]:
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
                    if cases is not None and (page_name, theme) not in cases:
                        continue
                    set_page(page, context, page_name, theme)
                    missing_fonts = [font for font in visual["requiredFonts"] if not font_face_available(page, font)]
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


def provenance_only_reference_ratification(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    provenance_fields = {"referencePackageSha256", "referenceApprovalCommit"}
    previous_contract = {key: value for key, value in previous.items() if key not in provenance_fields}
    current_contract = {key: value for key, value in current.items() if key not in provenance_fields}
    return (
        previous.get("referenceId") == current.get("referenceId")
        and previous.get("referencePackageSha256") != current.get("referencePackageSha256")
        and previous.get("referenceApprovalCommit") != current.get("referenceApprovalCommit")
        and previous_contract == current_contract
    )


def baseline_contract_key(value: dict[str, Any]) -> tuple[str, str, str]:
    provenance_fields = {"referencePackageSha256", "referenceApprovalCommit"}
    contract = {key: item for key, item in value.items() if key not in provenance_fields}
    digest = hashlib.sha256(
        json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return (
        digest,
        str(value.get("referencePackageSha256", "")),
        str(value.get("referenceApprovalCommit", "")),
    )


def independently_rejected_maintenance_baseline_snapshot(
    repo: Path,
    commit: str,
    head: str,
    relative: str,
) -> bool:
    """Recognize a rejected control candidate without erasing its adverse history."""
    try:
        from ui_change_gate import commit_paths, reviewed_preimplementation_maintenance_errors

        paths = commit_paths(repo, commit)
        if relative not in paths or reviewed_preimplementation_maintenance_errors(repo, commit, head, paths, []):
            return False
        inventory = git(
            repo,
            "ls-tree",
            "-r",
            "--name-only",
            head,
            "--",
            "planning/governance-migrations",
        ).splitlines()
        matches = []
        for record_path in inventory:
            if not re.fullmatch(r"planning/governance-migrations/GOV-MAINT-[0-9]{4}\.json", record_path):
                continue
            record, _, read_error = git_json_at(repo, head, record_path)
            if read_error or not isinstance(record, dict):
                continue
            attempts = record.get("reviewAttempts")
            if not isinstance(attempts, list):
                continue
            matches.extend(
                attempt
                for attempt in attempts
                if isinstance(attempt, dict)
                and attempt.get("reviewedCommit") == commit
                and attempt.get("disposition") == "CHANGES_REQUESTED"
            )
        return len(matches) == 1
    except OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError:
        return False


def baseline_history_errors(context: Context, baseline: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    relative = str(context.config["visual"]["baselinePath"])
    schema_path = confined_path(context.repo, "verification/desktop-ui-baseline.schema.json")
    schema = json_object(schema_path)
    if git(context.repo, "rev-parse", "--is-inside-work-tree") != "true":
        return [f"{relative}: cannot inspect governed Git history"]
    if git(context.repo, "rev-parse", "--is-shallow-repository") == "true":
        return [f"{relative}: visual baseline history requires a complete, non-shallow checkout"]
    status = git(context.repo, "status", "--porcelain=v1", "--", relative)
    if status:
        errors.append(f"{relative}: visual baseline must be committed before authoritative verification")
    head = git(context.repo, "rev-parse", "--verify", "HEAD")
    head_baseline, head_payload, head_error = git_json_at(context.repo, head, relative)
    if head_error:
        errors.append(head_error)
    elif head_baseline is None:
        errors.append(f"{relative}: visual baseline is absent from HEAD")
    elif head_payload != confined_path(context.repo, relative).read_bytes():
        errors.append(f"{relative}: working baseline bytes differ from the committed HEAD baseline")

    commits = git(context.repo, "rev-list", "--reverse", "--topo-order", head).splitlines()
    snapshots: dict[str, tuple[dict[str, Any] | None, bytes | None]] = {}
    valid_snapshots: dict[str, bool] = {}
    identities: dict[tuple[str, str], dict[str, str]] = {}
    package_cache: dict[tuple[str, str, str, bool], list[str]] = {}
    page_cache: dict[str, list[str] | None] = {}

    def snapshot(revision: str) -> tuple[dict[str, Any] | None, bytes | None]:
        if revision not in snapshots:
            value, payload, read_error = git_json_at(context.repo, revision, relative)
            snapshots[revision] = (value, payload)
            if read_error:
                errors.append(read_error)
        return snapshots[revision]

    def historical_pages(revision: str) -> list[str] | None:
        if revision in page_cache:
            return page_cache[revision]
        site, _, read_error = git_json_at(context.repo, revision, "design/ui-reference/SITE_MANIFEST.json")
        if read_error:
            errors.append(read_error)
            page_cache[revision] = None
            return None
        if site is None:
            errors.append(f"{revision}: approved route inventory is absent while a visual baseline exists")
            page_cache[revision] = None
            return None
        items = site.get("pages")
        pages = [str(item.get("file")) for item in items or [] if isinstance(item, dict)]
        if (
            not isinstance(items, list)
            or len(pages) != len(items)
            or len(pages) != len(set(pages))
            or not pages
            or any(not page.endswith(".html") for page in pages)
        ):
            errors.append(f"{revision}: approved route inventory is invalid for visual-baseline history")
            page_cache[revision] = None
            return None
        page_cache[revision] = pages
        return pages

    def baseline_pages(value: dict[str, Any], revision: str) -> list[str] | None:
        approval = value.get("referenceApprovalCommit")
        return (
            historical_pages(str(approval))
            if isinstance(approval, str) and re.fullmatch(r"[0-9a-f]{40}", approval)
            else historical_pages(revision)
        )

    ratified_legacy_contracts: set[tuple[str, str, str]] = set()
    ratification_handoff_commits: set[str] = set()
    for commit in commits:
        candidate, _ = snapshot(commit)
        if candidate is None:
            continue
        if baseline_document_errors(candidate, f"{commit}:{relative}", schema, baseline_pages(candidate, commit)):
            continue
        parents = git(context.repo, "rev-list", "--parents", "-n", "1", commit).split()[1:]
        for parent in parents:
            previous, _ = snapshot(parent)
            if previous is None or not provenance_only_reference_ratification(previous, candidate):
                continue
            if baseline_document_errors(previous, f"{parent}:{relative}", schema, baseline_pages(previous, parent)):
                continue
            if not approval_lineage_errors(context.repo, candidate, commit, package_cache):
                ratified_legacy_contracts.add(baseline_contract_key(previous))
                approval_commit = str(candidate.get("referenceApprovalCommit", ""))
                handoff_parents = git(context.repo, "rev-list", "--parents", "-n", "1", parent).split()[1:]
                if parent == approval_commit and len(handoff_parents) == 1:
                    before_handoff, before_handoff_payload = snapshot(handoff_parents[0])
                    _, handoff_payload = snapshot(parent)
                    if before_handoff == previous and before_handoff_payload == handoff_payload:
                        ratification_handoff_commits.add(parent)

    for commit in commits:
        current, current_payload = snapshot(commit)
        parents = git(context.repo, "rev-list", "--parents", "-n", "1", commit).split()[1:]
        if current is not None:
            document_errors = baseline_document_errors(
                current, f"{commit}:{relative}", schema, baseline_pages(current, commit)
            )
            errors.extend(document_errors)
            valid_snapshots[commit] = not document_errors
            lineage_introduction = not parents or not any(snapshot(parent)[1] == current_payload for parent in parents)
            if not document_errors and lineage_introduction and commit not in ratification_handoff_commits:
                rejected_maintenance_snapshot = independently_rejected_maintenance_baseline_snapshot(
                    context.repo,
                    commit,
                    head,
                    relative,
                )
                if not rejected_maintenance_snapshot:
                    errors.extend(
                        approval_lineage_errors(
                            context.repo,
                            current,
                            commit,
                            package_cache,
                            verify_package_at_original_approval=(
                                baseline_contract_key(current) not in ratified_legacy_contracts
                            ),
                        )
                    )
            identity = (str(current.get("referenceId", "")), str(current.get("referenceApprovalCommit", "")))
            if current_payload is not None:
                blob = hashlib.sha256(current_payload).hexdigest()
                identities.setdefault(identity, {}).setdefault(blob, commit)
        else:
            valid_snapshots[commit] = False
        for parent in parents or [""]:
            previous, previous_payload = snapshot(parent) if parent else (None, None)
            edge = f"{commit}<-{parent or '<root>'}"
            if previous is not None and current is None:
                errors.append(f"{edge}: visual baseline was removed from reachable history")
                continue
            if (
                previous is None
                or current is None
                or previous_payload == current_payload
                or not valid_snapshots.get(commit, False)
            ):
                continue
            if parent and parent not in valid_snapshots:
                parent_errors = baseline_document_errors(
                    previous,
                    f"{parent}:{relative}",
                    schema,
                    baseline_pages(previous, parent),
                )
                errors.extend(parent_errors)
                valid_snapshots[parent] = not parent_errors
            if parent and not valid_snapshots.get(parent, False):
                continue
            provenance_only = provenance_only_reference_ratification(previous, current)
            if current.get("referenceId") == previous.get("referenceId") and not provenance_only:
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
    baseline_schema = json_object(confined_path(context.repo, "verification/desktop-ui-baseline.schema.json"))
    errors.extend(
        baseline_document_errors(
            baseline,
            baseline_path.relative_to(context.repo).as_posix(),
            baseline_schema,
            context.pages,
        )
    )
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
        retry_cases = {
            (page_name, theme)
            for key in changed
            for page_name, separator, theme in [key.partition("::")]
            if separator and page_name in context.pages and theme in context.config["visual"]["colorSchemes"]
        }
        if retry_cases and len(retry_cases) == len(changed) and len(retry_cases) <= 3:
            retry_one, retry_one_errors = render_visuals(context, retry_cases)
            errors.extend(retry_one_errors)
            expected_retry = {key: expected_entries.get(key) for key in changed}
            observed_retry = {key: retry_one.get(key) for key in changed}
            if observed_retry == expected_retry and not retry_one_errors:
                retry_two, retry_two_errors = render_visuals(context, retry_cases)
                errors.extend(retry_two_errors)
                if {key: retry_two.get(key) for key in changed} == expected_retry and not retry_two_errors:
                    return result(
                        context,
                        "visual",
                        errors,
                        {"captures": len(observed), "settings": context.config["visual"], "stabilizedRetries": 2},
                    )
            elif observed_retry != {key: observed.get(key) for key in changed}:
                errors.append(f"{source(context, 'pages')}: visual capture is not deterministic for {changed[0]}")
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
