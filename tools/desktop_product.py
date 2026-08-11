#!/usr/bin/env python3
"""Load and verify the functional desktop product bundle, never the UI reference fixture."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from ui_conformance import confined_path, file_inventory, stable_file_bytes

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


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def product_build_errors(repo: Path) -> list[str]:
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
            expected_sources[relative] = sha256(stable_file_bytes(repo, confined_path(repo, relative)))
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
        activation = json.loads(
            stable_file_bytes(repo, confined_path(repo, "verification/extensions/desktop-ui.json"))
        )
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"desktop product/reference boundary cannot be loaded: {exc}")
        return errors
    if tauri.get("build", {}).get("frontendDist") != "../product-dist":
        errors.append("Tauri production and development must serve only apps/desktop/product-dist")
    if (
        manifest.get("referenceId") != activation.get("referenceId")
        or manifest.get("referencePackageSha256") != activation.get("referencePackageSha256")
    ):
        errors.append("desktop product manifest does not bind the approved design reference identity")
    reference_pages = {
        item.get("file") for item in reference_site.get("pages", []) if isinstance(item, dict)
    }
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
    """Return the exact product document with its local CSS/ES module embedded for offline browser checks."""
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
