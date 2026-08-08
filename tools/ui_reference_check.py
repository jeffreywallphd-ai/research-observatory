#!/usr/bin/env python3
"""Validate the governed Research Observatory UI reference.

This checker treats the approved HTML/style/workflow package as a normative
experience contract without mistaking illustrative mock content for product
requirements. It can also compare an implementation manifest emitted by the
real desktop application against the approved routes, workflow profiles, and
reference ID.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

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


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a mapping")
    return data


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain an object")
    return data


def normalized_routes(values: list[str]) -> set[str]:
    result: set[str] = set()
    for value in values:
        v = value.strip().split("?", 1)[0].split("#", 1)[0]
        if not v:
            continue
        result.add(v.rsplit("/", 1)[-1])
    return result


def validate(reference: Path, implementation_manifest: Path | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    for name in GOVERNANCE_FILES:
        if not (reference / name).is_file():
            errors.append(f"missing governed reference artifact: {name}")
    if errors:
        return {"ok": False, "reference": str(reference), "errors": errors, "warnings": warnings}

    try:
        approval = load_yaml(reference / "APPROVAL.yaml")
        manifest = load_yaml(reference / "REFERENCE_MANIFEST.yaml")
        site = load_json(reference / "SITE_MANIFEST.json")
        coverage = load_json(reference / "CAPABILITY_COVERAGE.json")
        workflows = load_json(reference / "WORKFLOW_CATALOG.json")
    except (ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        errors.append(str(exc))
        return {"ok": False, "reference": str(reference), "errors": errors, "warnings": warnings}

    ids = {
        "approval": approval.get("reference_id"),
        "manifest": manifest.get("reference_id"),
        "site": site.get("reference_id"),
        "coverage": coverage.get("reference_id"),
        "workflows": workflows.get("reference_id"),
    }
    if len({v for v in ids.values() if v}) != 1 or any(not v for v in ids.values()):
        errors.append(f"reference IDs disagree or are missing: {ids}")
    reference_id = next((v for v in ids.values() if v), None)

    if approval.get("status") != "approved":
        errors.append(f"reference is not approved: status={approval.get('status')!r}")
    if manifest.get("status") != "approved":
        errors.append(f"manifest is not approved: status={manifest.get('status')!r}")

    pages = site.get("pages") or []
    if not isinstance(pages, list):
        errors.append("SITE_MANIFEST pages must be a list")
        pages = []
    page_files = {p.get("file") for p in pages if isinstance(p, dict) and p.get("file")}
    expected_count = int(site.get("product_page_count") or 0)
    if expected_count != 32 or len(page_files) != 32:
        errors.append(f"approved reference must contain 32 product pages; manifest={expected_count}, unique={len(page_files)}")

    for file_name in sorted(page_files):
        path = reference / file_name
        if not path.is_file():
            errors.append(f"missing product page: {file_name}")
            continue
        html = path.read_text(encoding="utf-8")
        for marker in ("data-workflow-select", "data-workflow-nav", "data-workflow-context"):
            if marker not in html:
                errors.append(f"{file_name}: missing adaptive-workflow marker {marker}")
        if 'href="assets/tokens.css"' not in html or 'href="assets/app.css"' not in html:
            errors.append(f"{file_name}: does not use the shared canonical stylesheets")

    wf_map = workflows.get("workflows") or {}
    if not isinstance(wf_map, dict) or len(wf_map) != 14:
        errors.append(f"workflow catalog must define exactly fourteen profiles; found {len(wf_map) if isinstance(wf_map, dict) else 'invalid'}")
        wf_map = {}
    for key, profile in wf_map.items():
        steps = profile.get("steps") if isinstance(profile, dict) else None
        if not isinstance(steps, list) or not steps:
            errors.append(f"workflow {key}: missing ordered steps")
            continue
        for step in steps:
            if step not in page_files:
                errors.append(f"workflow {key}: step is not a governed product page: {step}")
        if not profile.get("purpose") or not profile.get("output"):
            errors.append(f"workflow {key}: purpose and output are required")

    cov_pages = coverage.get("page_contracts") or {}
    if not isinstance(cov_pages, dict):
        errors.append("CAPABILITY_COVERAGE page_contracts must be an object")
        cov_pages = {}
    missing_contracts = sorted(page_files - set(cov_pages))
    if missing_contracts:
        errors.append(f"product pages missing page contracts: {', '.join(missing_contracts)}")
    for file_name, contract in cov_pages.items():
        if file_name in page_files and not contract.get("required_regions"):
            errors.append(f"{file_name}: page contract has no required regions")

    hashes = manifest.get("file_hashes") or {}
    governed = manifest.get("governed_files") or []
    if not governed or not hashes:
        errors.append("REFERENCE_MANIFEST has no governed file/hash set; regenerate it before approval")
    else:
        for rel in governed:
            path = reference / rel
            if not path.is_file():
                errors.append(f"governed file missing: {rel}")
                continue
            expected = hashes.get(rel)
            actual = sha256(path)
            if not expected:
                errors.append(f"governed file has no recorded hash: {rel}")
            elif expected != actual:
                errors.append(f"governed file hash mismatch: {rel}")

    implementation: dict[str, Any] | None = None
    if implementation_manifest:
        implementation = load_json(implementation_manifest)
        if implementation.get("ui_reference_id") != reference_id:
            errors.append(
                "implementation manifest does not cite the approved UI reference: "
                f"expected {reference_id}, got {implementation.get('ui_reference_id')}"
            )
        app_routes = normalized_routes(list(implementation.get("routes") or []))
        missing_routes = sorted(page_files - app_routes)
        if missing_routes:
            errors.append(f"implementation is missing governed routes/pages: {', '.join(missing_routes)}")
        app_profiles = implementation.get("workflow_profiles") or {}
        if not isinstance(app_profiles, dict):
            errors.append("implementation workflow_profiles must be an object")
        else:
            for key, profile in wf_map.items():
                expected_steps = profile.get("steps") or []
                actual_steps = (app_profiles.get(key) or {}).get("steps")
                if actual_steps != expected_steps:
                    errors.append(f"implementation workflow differs from approved catalog: {key}")
        token_hash = implementation.get("token_file_sha256")
        approved_token_hash = sha256(reference / "assets/tokens.css")
        if token_hash and token_hash != approved_token_hash:
            errors.append("implementation token hash differs from approved assets/tokens.css")
        elif not token_hash:
            warnings.append("implementation manifest did not provide token_file_sha256")

    return {
        "ok": not errors,
        "reference": str(reference),
        "reference_id": reference_id,
        "approved": approval.get("status") == "approved",
        "product_pages": len(page_files),
        "workflow_profiles": len(wf_map),
        "governed_files": len(governed),
        "implementation_manifest": str(implementation_manifest) if implementation_manifest else None,
        "errors": errors,
        "warnings": warnings,
    }


def write_hashes(reference: Path) -> None:
    manifest_path = reference / "REFERENCE_MANIFEST.yaml"
    manifest = load_yaml(manifest_path)
    excluded = {"REFERENCE_MANIFEST.yaml", "SHA256SUMS.txt", "VALIDATION_REPORT.md", "ui-reference-validation.json"}
    governed: list[str] = []
    for path in sorted(reference.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(reference).as_posix()
        if rel in excluded or rel.startswith("previews/") or "__pycache__" in rel:
            continue
        governed.append(rel)
    manifest["governed_files"] = governed
    manifest["file_hashes"] = {rel: sha256(reference / rel) for rel in governed}
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=Path("design/ui-reference"))
    parser.add_argument("--implementation-manifest", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--write-hashes", action="store_true", help="Regenerate governed-file hashes for a proposed/approved reference revision.")
    args = parser.parse_args()

    reference = args.reference.resolve()
    if args.write_hashes:
        write_hashes(reference)
    result = validate(reference, args.implementation_manifest)
    output = json.dumps(result, indent=2, ensure_ascii=False)
    print(output)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output + "\n", encoding="utf-8")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
