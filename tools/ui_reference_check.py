#!/usr/bin/env python3
"""Validate the approved UI reference and emit deterministic machine evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

try:
    import yaml
except ImportError as exc:  # pragma: no cover - actionable bootstrap failure
    raise SystemExit("PyYAML is required: install project development dependencies first.") from exc

GOVERNANCE_FILES = (
    "APPROVAL.yaml",
    "REFERENCE_MANIFEST.yaml",
    "SITE_MANIFEST.json",
    "CAPABILITY_COVERAGE.json",
    "WORKFLOW_CATALOG.json",
    "STYLE_GUIDE.md",
    "PAGE_INVENTORY.md",
)
INVENTORY_EXCLUSIONS = frozenset(
    {"REFERENCE_MANIFEST.yaml", "SHA256SUMS.txt", "VALIDATION_REPORT.md", "ui-reference-validation.json"}
)
TEXT_SUFFIXES = frozenset({".css", ".html", ".js", ".json", ".md", ".py", ".txt", ".yaml", ".yml"})
REQUIRED_SHARED_ASSETS = frozenset({"assets/tokens.css", "assets/app.css", "assets/print.css", "assets/app.js"})
HOSTED_ROUTE = re.compile(
    r"(?:^|[-_/])(?:admin|administrator|administration|billing|cloud-admin|cloud-ops|managed-cloud|tenant)"
    r"(?:[-_./]|$)",
    re.IGNORECASE,
)
SHA256 = re.compile(r"^[0-9a-f]{64}$")
CSS_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE | re.DOTALL)
CSS_IMPORT = re.compile(r"@import\s+(?!url\()(['\"])(.*?)\1", re.IGNORECASE | re.DOTALL)
BROWSER_NETWORK_API = re.compile(
    r"\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|Worker|SharedWorker|importScripts)\s*\("
    r"|\bnavigator\s*\.\s*(?:sendBeacon|serviceWorker\s*\.\s*register)\s*\("
    r"|\b(?:audioWorklet|paintWorklet)\s*\.\s*addModule\s*\(",
    re.IGNORECASE,
)
REMOTE_RESOURCE = re.compile(r"(?:https?:)?//[^\s'\"<>]+", re.IGNORECASE)
FETCH_ATTRIBUTES = {
    "a": ("href",),
    "applet": ("archive", "code", "codebase", "object"),
    "audio": ("src",),
    "base": ("href",),
    "body": ("background",),
    "button": ("formaction",),
    "embed": ("src",),
    "feimage": ("href", "xlink:href"),
    "form": ("action",),
    "frame": ("src",),
    "html": ("manifest",),
    "iframe": ("src",),
    "image": ("href", "xlink:href"),
    "img": ("src", "srcset"),
    "input": ("src", "formaction"),
    "link": ("href",),
    "menuitem": ("icon",),
    "object": ("data",),
    "portal": ("src",),
    "script": ("src", "href", "xlink:href"),
    "source": ("src", "srcset"),
    "table": ("background",),
    "td": ("background",),
    "th": ("background",),
    "track": ("src",),
    "tr": ("background",),
    "use": ("href", "xlink:href"),
    "video": ("src", "poster"),
}


class ReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.targets: list[tuple[str, str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        for attribute in FETCH_ATTRIBUTES.get(tag, ()):
            value = values.get(attribute)
            if not value:
                continue
            targets = [item.strip().split()[0] for item in value.split(",")] if attribute == "srcset" else [value]
            self.targets.extend((tag, attribute, target) for target in targets if target)
        if tag == "meta" and (values.get("http-equiv") or "").lower() == "refresh":
            match = re.search(r"(?:^|;)\s*url\s*=\s*([^;]+)", values.get("content") or "", re.IGNORECASE)
            if match:
                self.targets.append((tag, "content", match.group(1).strip(" \t'\"")))


def canonical_payload(path: str, payload: bytes) -> bytes:
    return payload.replace(b"\r\n", b"\n") if Path(path).suffix.lower() in TEXT_SUFFIXES else payload


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(canonical_payload(path.name, path.read_bytes()))


def nonredirected_file(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if not relative or pure.is_absolute() or "\\" in relative or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError(f"noncanonical reference path: {relative!r}")
    path = root.joinpath(*pure.parts)
    cursor = root
    for part in pure.parts:
        cursor /= part
        if cursor.is_symlink() or cursor.is_junction():
            raise ValueError(f"reference path is redirected: {relative}")
    if path.resolve(strict=True) != path or not path.is_file():
        raise ValueError(f"reference path is not a canonical file: {relative}")
    return path


def snapshot(root: Path, relative: str, errors: list[str]) -> bytes | None:
    try:
        return nonredirected_file(root, relative).read_bytes()
    except (OSError, ValueError) as exc:
        errors.append(f"cannot read governed reference artifact {relative}: {exc}")
        return None


def load_yaml_bytes(name: str, payload: bytes) -> dict[str, Any]:
    data = yaml.safe_load(payload.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{name} must contain a mapping")
    return data


def load_json_bytes(name: str, payload: bytes) -> dict[str, Any]:
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{name} must contain an object")
    return data


def normalized_routes(values: list[str]) -> set[str]:
    result: set[str] = set()
    for value in values:
        route = value.strip().split("?", 1)[0].split("#", 1)[0]
        if route:
            result.add(route.rsplit("/", 1)[-1])
    return result


def discovered_inventory(reference: Path, errors: list[str]) -> list[str]:
    discovered: list[str] = []

    def visit(directory: Path) -> None:
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            errors.append(f"cannot enumerate UI-reference inventory at {directory}: {exc}")
            return
        for entry in entries:
            path = Path(entry.path)
            relative = path.relative_to(reference).as_posix()
            if relative.startswith("previews/") or "__pycache__" in relative:
                continue
            try:
                redirected = entry.is_symlink() or path.is_junction()
                directory_entry = entry.is_dir(follow_symlinks=False)
                file_entry = entry.is_file(follow_symlinks=False)
            except OSError as exc:
                errors.append(f"cannot inspect UI-reference inventory path {relative}: {exc}")
                continue
            if redirected:
                errors.append(f"UI-reference inventory path is redirected: {relative}")
            elif directory_entry:
                visit(path)
            elif file_entry and relative not in INVENTORY_EXCLUSIONS:
                discovered.append(relative)

    visit(reference)
    return sorted(discovered)


def local_target_error(reference: Path, source: str, raw_target: str, context: str) -> tuple[str | None, str | None]:
    parsed = urlparse(raw_target)
    if raw_target.startswith("#"):
        return None, None
    if parsed.scheme or parsed.netloc:
        return None, f"{source}: network-dependent {context}: {raw_target}"
    target_text = unquote(parsed.path)
    if not target_text:
        return None, None
    if "\\" in target_text or target_text.startswith("/"):
        return None, f"{source}: package-escaping local reference: {raw_target}"
    root = reference.resolve(strict=True)
    target = (reference / PurePosixPath(source).parent / PurePosixPath(target_text)).resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError:
        return None, f"{source}: package-escaping local reference: {raw_target}"
    if not target.is_file():
        return None, f"{source}: broken local reference: {raw_target}"
    return target.relative_to(root).as_posix(), None


def executable_reference_errors(reference: Path, payloads: dict[str, bytes]) -> list[str]:
    errors: list[str] = []
    for relative, payload in sorted(payloads.items()):
        suffix = Path(relative).suffix.lower()
        if suffix not in {".css", ".html", ".js"}:
            continue
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            errors.append(f"{relative}: executable browser content is not UTF-8: {exc}")
            continue
        if suffix in {".css", ".html"}:
            css_targets = [match.group(2).strip() for match in CSS_URL.finditer(text)]
            css_targets.extend(match.group(2).strip() for match in CSS_IMPORT.finditer(text))
            for target in css_targets:
                _, error = local_target_error(reference, relative, target, "CSS reference")
                if error:
                    errors.append(error)
        if suffix in {".html", ".js"} and BROWSER_NETWORK_API.search(text):
            errors.append(f"{relative}: browser network API is prohibited in the offline reference")
        for match in REMOTE_RESOURCE.finditer(text):
            errors.append(f"{relative}: remote browser resource is prohibited: {match.group(0)}")
    return errors


def html_reference_errors(reference: Path, payloads: dict[str, bytes], html_files: set[str]) -> list[str]:
    errors: list[str] = []
    for relative in sorted(html_files):
        payload = payloads.get(relative)
        if payload is None:
            continue
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            errors.append(f"{relative}: HTML is not UTF-8: {exc}")
            continue
        parser = ReferenceParser()
        parser.feed(text)
        linked_assets: set[str] = set()
        for tag, attribute, raw_target in parser.targets:
            destination, error = local_target_error(reference, relative, raw_target, f"{tag} {attribute}")
            if error:
                errors.append(error)
            elif destination:
                linked_assets.add(destination)
                if HOSTED_ROUTE.search(destination):
                    errors.append(f"{relative}: unexpected hosted administration route: {destination}")
        if relative in html_files and not REQUIRED_SHARED_ASSETS.issubset(linked_assets):
            missing = sorted(REQUIRED_SHARED_ASSETS - linked_assets)
            errors.append(f"{relative}: missing shared local assets: {', '.join(missing)}")
    return errors


def generator_reproducibility_errors(
    payloads: dict[str, bytes], manifest_payload: bytes, expected_hashes: dict[str, str]
) -> list[str]:
    errors: list[str] = []
    with tempfile.TemporaryDirectory() as temporary:
        target = Path(temporary) / "ui-reference"
        try:
            for relative, payload in {**payloads, "REFERENCE_MANIFEST.yaml": manifest_payload}.items():
                path = target.joinpath(*PurePosixPath(relative).parts)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
            generated_outputs = {
                relative
                for relative in expected_hashes
                if relative.endswith(".html") or relative in {"PAGE_INVENTORY.md", "README.md", "STYLE_GUIDE.md"}
            }
            for relative in generated_outputs:
                target.joinpath(*PurePosixPath(relative).parts).unlink()
            generated = subprocess.run(
                [sys.executable, str(target / "scripts" / "build_mockups.py")],
                cwd=target,
                capture_output=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return [f"UI-reference generator could not be reproduced: {exc}"]
        if generated.returncode != 0:
            message = generated.stderr.decode("utf-8", errors="replace").strip()
            return [f"UI-reference generator failed with exit {generated.returncode}: {message}"]
        inventory_errors: list[str] = []
        actual_inventory = discovered_inventory(target, inventory_errors)
        errors.extend(inventory_errors)
        if actual_inventory != sorted(expected_hashes):
            missing = sorted(set(expected_hashes) - set(actual_inventory))
            unexpected = sorted(set(actual_inventory) - set(expected_hashes))
            errors.append(f"UI-reference generator inventory differs; missing={missing}, unexpected={unexpected}")
        for relative, expected in sorted(expected_hashes.items()):
            path = target.joinpath(*PurePosixPath(relative).parts)
            if not path.is_file():
                errors.append(f"UI-reference generator removed governed file: {relative}")
                continue
            actual = sha256_bytes(canonical_payload(relative, path.read_bytes()))
            if actual != expected:
                errors.append(f"UI-reference generator is not reproducible for {relative}")
    return errors


def stability_errors(reference: Path, initial: dict[str, bytes], expected_inventory: list[str]) -> list[str]:
    errors: list[str] = []
    if discovered_inventory(reference, errors) != sorted(expected_inventory):
        errors.append("UI-reference inventory changed during validation")
    for relative, payload in initial.items():
        current = snapshot(reference, relative, errors)
        if current is not None and current != payload:
            errors.append(f"UI-reference file changed during validation: {relative}")
    return errors


def validate(reference: Path, implementation_manifest: Path | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    reference = reference.absolute()
    try:
        if reference.is_symlink() or reference.is_junction() or reference.resolve(strict=True) != reference:
            raise ValueError("reference root is redirected or noncanonical")
    except (OSError, ValueError) as exc:
        return {"ok": False, "reference": reference.name, "errors": [str(exc)], "warnings": []}

    controls: dict[str, bytes] = {}
    for name in GOVERNANCE_FILES:
        payload = snapshot(reference, name, errors)
        if payload is not None:
            controls[name] = payload
    if errors:
        return {"ok": False, "reference": reference.name, "errors": errors, "warnings": warnings}
    try:
        approval = load_yaml_bytes("APPROVAL.yaml", controls["APPROVAL.yaml"])
        manifest = load_yaml_bytes("REFERENCE_MANIFEST.yaml", controls["REFERENCE_MANIFEST.yaml"])
        site = load_json_bytes("SITE_MANIFEST.json", controls["SITE_MANIFEST.json"])
        coverage = load_json_bytes("CAPABILITY_COVERAGE.json", controls["CAPABILITY_COVERAGE.json"])
        workflows = load_json_bytes("WORKFLOW_CATALOG.json", controls["WORKFLOW_CATALOG.json"])
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        return {"ok": False, "reference": reference.name, "errors": [str(exc)], "warnings": warnings}

    ids = {
        "approval": approval.get("reference_id"),
        "manifest": manifest.get("reference_id"),
        "site": site.get("reference_id"),
        "coverage": coverage.get("reference_id"),
        "workflows": workflows.get("reference_id"),
    }
    if len({value for value in ids.values() if value}) != 1 or any(not value for value in ids.values()):
        errors.append(f"reference IDs disagree or are missing: {ids}")
    reference_id = next((value for value in ids.values() if isinstance(value, str) and value), None)
    if approval.get("status") != "approved":
        errors.append(f"reference is not approved: status={approval.get('status')!r}")
    if manifest.get("status") != "approved":
        errors.append(f"manifest is not approved: status={manifest.get('status')!r}")
    if approval.get("version") != manifest.get("version") or site.get("version") != manifest.get("version"):
        errors.append("approved reference version disagrees across governance records")

    governed_raw = manifest.get("governed_files")
    hashes_raw = manifest.get("file_hashes")
    governed = governed_raw if isinstance(governed_raw, list) else []
    hashes = hashes_raw if isinstance(hashes_raw, dict) else {}
    if not governed or any(not isinstance(item, str) or not item for item in governed):
        errors.append("REFERENCE_MANIFEST governed_files must be a nonempty string array")
        governed = []
    elif len(governed) != len(set(governed)):
        errors.append("REFERENCE_MANIFEST governed_files contains duplicates")
    if not hashes or any(not isinstance(key, str) or not isinstance(value, str) for key, value in hashes.items()):
        errors.append("REFERENCE_MANIFEST file_hashes must be a nonempty string map")
        hashes = {}
    elif set(hashes) != set(governed):
        errors.append("REFERENCE_MANIFEST governed_files and file_hashes inventories differ")
    for relative, digest in hashes.items():
        if not SHA256.fullmatch(digest):
            errors.append(f"governed file has an invalid SHA-256: {relative}")

    discovered = discovered_inventory(reference, errors)
    if sorted(governed) != discovered:
        missing = sorted(set(governed) - set(discovered))
        unexpected = sorted(set(discovered) - set(governed))
        errors.append(f"governed inventory mismatch; missing={missing}, unexpected={unexpected}")

    payloads: dict[str, bytes] = {}
    observed_hashes: dict[str, str] = {}
    for relative in governed:
        payload = snapshot(reference, relative, errors)
        if payload is None:
            continue
        payloads[relative] = payload
        actual = sha256_bytes(canonical_payload(relative, payload))
        observed_hashes[relative] = actual
        if hashes.get(relative) != actual:
            errors.append(f"governed file hash mismatch: {relative}")

    pages = site.get("pages")
    if not isinstance(pages, list):
        errors.append("SITE_MANIFEST pages must be a list")
        pages = []
    page_files = {
        file_name
        for page in pages
        if isinstance(page, dict) and isinstance(file_name := page.get("file"), str) and file_name
    }
    declared_product_pages = site.get("product_page_count")
    if (
        not isinstance(declared_product_pages, int)
        or isinstance(declared_product_pages, bool)
        or declared_product_pages < 1
        or declared_product_pages != len(page_files)
        or declared_product_pages != len(pages)
    ):
        errors.append(
            "approved reference product-page inventory is inconsistent; "
            f"manifest={declared_product_pages!r}, entries={len(pages)}, unique={len(page_files)}"
        )
    html_files = {relative for relative in governed if relative.endswith(".html")}
    declared_html_documents = site.get("html_document_count")
    if (
        not isinstance(declared_html_documents, int)
        or isinstance(declared_html_documents, bool)
        or declared_html_documents < 1
        or declared_html_documents != len(html_files)
    ):
        errors.append(
            f"approved reference HTML inventory is inconsistent; manifest={declared_html_documents!r}, "
            f"governed={len(html_files)}"
        )
    for file_name in sorted(page_files):
        if HOSTED_ROUTE.search(file_name):
            errors.append(f"unexpected hosted administration route: {file_name}")
        payload = payloads.get(file_name)
        if payload is None:
            errors.append(f"missing product page: {file_name}")
            continue
        text = payload.decode("utf-8", errors="replace")
        for marker in ("data-workflow-select", "data-workflow-nav", "data-workflow-context"):
            if marker not in text:
                errors.append(f"{file_name}: missing adaptive-workflow marker {marker}")

    workflow_map = workflows.get("workflows")
    if not isinstance(workflow_map, dict) or len(workflow_map) != 14:
        found = len(workflow_map) if isinstance(workflow_map, dict) else "invalid"
        errors.append(f"workflow catalog must define exactly fourteen profiles; found {found}")
        workflow_map = {}
    for key, profile in workflow_map.items():
        steps = profile.get("steps") if isinstance(profile, dict) else None
        if not isinstance(steps, list) or not steps or any(not isinstance(step, str) for step in steps):
            errors.append(f"workflow {key}: missing valid ordered steps")
            continue
        for step in steps:
            if step not in page_files:
                errors.append(f"workflow {key}: step is not a governed product page: {step}")
        if not profile.get("purpose") or not profile.get("output"):
            errors.append(f"workflow {key}: purpose and output are required")

    contract_map = coverage.get("page_contracts")
    if not isinstance(contract_map, dict):
        errors.append("CAPABILITY_COVERAGE page_contracts must be an object")
        contract_map = {}
    missing_contracts = sorted(page_files - set(contract_map))
    extra_contracts = sorted(set(contract_map) - page_files)
    if missing_contracts or extra_contracts:
        errors.append(
            f"page contracts must exactly match product pages; missing={missing_contracts}, extra={extra_contracts}"
        )
    for file_name, contract in contract_map.items():
        if file_name in page_files and (not isinstance(contract, dict) or not contract.get("required_regions")):
            errors.append(f"{file_name}: page contract has no required regions")
    capabilities = coverage.get("capabilities")
    if not isinstance(capabilities, list) or len(capabilities) != 20:
        errors.append("CAPABILITY_COVERAGE must contain exactly 20 capability records")
    inventory_text = controls["PAGE_INVENTORY.md"].decode("utf-8", errors="replace")
    missing_inventory_pages = sorted(file_name for file_name in page_files if file_name not in inventory_text)
    if missing_inventory_pages:
        errors.append(f"PAGE_INVENTORY.md omits product pages: {', '.join(missing_inventory_pages)}")

    errors.extend(html_reference_errors(reference, payloads, html_files))
    errors.extend(executable_reference_errors(reference, payloads))
    if hashes:
        errors.extend(generator_reproducibility_errors(payloads, controls["REFERENCE_MANIFEST.yaml"], hashes))

    implementation: dict[str, Any] | None = None
    if implementation_manifest:
        try:
            implementation = load_json_bytes(implementation_manifest.name, implementation_manifest.read_bytes())
        except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"cannot read implementation manifest: {exc}")
            implementation = {}
        if implementation.get("ui_reference_id") != reference_id:
            errors.append(
                "implementation manifest does not cite the approved UI reference: "
                f"expected {reference_id}, got {implementation.get('ui_reference_id')}"
            )
        app_routes = normalized_routes(list(implementation.get("routes") or []))
        missing_routes = sorted(page_files - app_routes)
        if missing_routes:
            errors.append(f"implementation is missing governed routes/pages: {', '.join(missing_routes)}")
        app_profiles = implementation.get("workflow_profiles")
        if not isinstance(app_profiles, dict):
            errors.append("implementation workflow_profiles must be an object")
        else:
            for key, profile in workflow_map.items():
                if (app_profiles.get(key) or {}).get("steps") != profile.get("steps"):
                    errors.append(f"implementation workflow differs from approved catalog: {key}")
        token_hash = implementation.get("token_file_sha256")
        approved_token_hash = hashes.get("assets/tokens.css")
        if token_hash and token_hash != approved_token_hash:
            errors.append("implementation token hash differs from approved assets/tokens.css")
        elif not token_hash:
            warnings.append("implementation manifest did not provide token_file_sha256")

    stable_snapshots = dict(payloads)
    stable_snapshots["REFERENCE_MANIFEST.yaml"] = controls["REFERENCE_MANIFEST.yaml"]
    errors.extend(stability_errors(reference, stable_snapshots, governed))

    package_hash = sha256_bytes(
        json.dumps(observed_hashes, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return {
        "ok": not errors,
        "reference": reference.name,
        "reference_id": reference_id,
        "reference_version": manifest.get("version"),
        "approved": approval.get("status") == "approved",
        "product_pages": len(page_files),
        "html_documents": len(html_files),
        "workflow_profiles": len(workflow_map),
        "capability_records": len(capabilities) if isinstance(capabilities, list) else 0,
        "governed_files": len(governed),
        "governed_hashes": dict(sorted(observed_hashes.items())),
        "reference_package_sha256": package_hash,
        "generator_reproducible": not any("generator" in error.lower() for error in errors),
        "implementation_manifest": implementation_manifest.name if implementation_manifest else None,
        "errors": errors,
        "warnings": warnings,
    }


def write_hashes(reference: Path) -> None:
    approval = load_yaml_bytes("APPROVAL.yaml", nonredirected_file(reference, "APPROVAL.yaml").read_bytes())
    if approval.get("status") == "approved":
        raise ValueError("refusing to rewrite hashes for an approved UI reference; create a proposed revision first")
    manifest_path = nonredirected_file(reference, "REFERENCE_MANIFEST.yaml")
    manifest = load_yaml_bytes("REFERENCE_MANIFEST.yaml", manifest_path.read_bytes())
    errors: list[str] = []
    governed = discovered_inventory(reference, errors)
    if errors:
        raise ValueError("; ".join(errors))
    manifest["governed_files"] = governed
    manifest["file_hashes"] = {
        relative: sha256_bytes(canonical_payload(relative, nonredirected_file(reference, relative).read_bytes()))
        for relative in governed
    }
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8", newline="\n"
    )


def confined_report(repo: Path, raw_path: Path) -> Path:
    root = (repo / "artifacts" / "tmp").absolute()
    destination = (raw_path if raw_path.is_absolute() else repo / raw_path).absolute()
    try:
        if root.resolve(strict=True) != root or root.is_symlink() or root.is_junction():
            raise ValueError("report root is redirected")
        destination.parent.resolve(strict=True).relative_to(root)
        if destination.parent.resolve(strict=True) != destination.parent:
            raise ValueError("report parent is redirected")
    except (OSError, ValueError) as exc:
        raise ValueError("UI-reference report must remain under canonical artifacts/tmp") from exc
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--reference", type=Path, default=Path("design/ui-reference"))
    parser.add_argument("--implementation-manifest", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--write-hashes", action="store_true", help="Regenerate hashes for a proposed revision only.")
    args = parser.parse_args()

    repo = args.repo.resolve(strict=True)
    reference = (args.reference if args.reference.is_absolute() else repo / args.reference).absolute()
    try:
        reference.relative_to(repo)
        if args.write_hashes:
            write_hashes(reference)
        result = validate(reference, args.implementation_manifest)
        output = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        print(output, end="")
        if args.report:
            destination = confined_report(repo, args.report)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="\n", dir=destination.parent, prefix=destination.name, delete=False
            ) as handle:
                temporary = Path(handle.name)
                handle.write(output)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
