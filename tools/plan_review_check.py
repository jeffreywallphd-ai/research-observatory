#!/usr/bin/env python3
"""Validate the generated static capability/slice planning review site."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: missing YAML front matter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError(f"{path}: unterminated YAML front matter")
    return yaml.safe_load(text[4:end]) or {}


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []
        self.scripts: list[str] = []
        self.styles: list[str] = []
        self.ids: list[str] = []
        self.decision_ids: list[str] = []
        self.title_count = 0
        self.h1_count = 0
        self.other_choice_count = 0
        self.other_input_count = 0
        self.rationale_count = 0
        self.planning_nav_count = 0
        self.planning_tab_names: list[str] = []
        self.planning_panel_names: list[str] = []
        self.html_lang: str | None = None
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value for key, value in attrs}
        if tag == "html":
            self.html_lang = values.get("lang")
        if tag == "a" and values.get("href"):
            self.hrefs.append(values["href"] or "")
        if tag == "script" and values.get("src"):
            self.scripts.append(values["src"] or "")
        if tag == "link" and values.get("rel") == "stylesheet" and values.get("href"):
            self.styles.append(values["href"] or "")
        if values.get("id"):
            self.ids.append(values["id"] or "")
        if values.get("data-decision-id"):
            self.decision_ids.append(values["data-decision-id"] or "")
        if "data-other-choice" in values:
            self.other_choice_count += 1
        if "data-decision-other" in values:
            self.other_input_count += 1
        if "data-decision-rationale" in values:
            self.rationale_count += 1
        if "data-planning-nav" in values:
            self.planning_nav_count += 1
        if values.get("data-nav-tab"):
            self.planning_tab_names.append(values["data-nav-tab"] or "")
        if values.get("data-nav-panel"):
            self.planning_panel_names.append(values["data-nav-panel"] or "")
        if tag == "title":
            self.title_count += 1
        if tag == "h1":
            self.h1_count += 1

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.text_parts.append(data.strip())


def local_target(page: Path, href: str) -> Path | None:
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc or href.startswith("#") or href.startswith("mailto:"):
        return None
    raw_path = parsed.path
    if not raw_path:
        return None
    return (page.parent / raw_path).resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--site", default="planning/review-site")
    parser.add_argument("--report")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    site = (repo / args.site).resolve() if not Path(args.site).is_absolute() else Path(args.site).resolve()
    errors: list[str] = []
    warnings: list[str] = []

    manifest_path = site / "manifest.json"
    if not manifest_path.exists():
        errors.append(f"Missing review-site manifest: {manifest_path}")
        manifest: dict[str, Any] = {"capabilities": []}
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    cap_plans = {path.stem: path for path in (repo / "planning/capability-plans").glob("CAP-*.md")}
    slice_plans: dict[str, Path] = {}
    for path in (repo / "planning/slice-plans").glob("CAP-*/*.md"):
        meta = frontmatter(path)
        slice_plans[meta["slice_id"]] = path

    manifest_caps = {entry["capability_id"]: entry for entry in manifest.get("capabilities", [])}
    if set(manifest_caps) != set(cap_plans):
        errors.append(
            f"Manifest capability set differs from plans: manifest={sorted(manifest_caps)} plans={sorted(cap_plans)}"
        )

    manifest_slices: dict[str, dict[str, Any]] = {}
    for cap_entry in manifest.get("capabilities", []):
        cid = cap_entry["capability_id"]
        plan_path = repo / cap_entry["plan_path"]
        if not plan_path.exists():
            errors.append(f"{cid}: missing capability plan {plan_path}")
        elif sha256(plan_path) != cap_entry.get("plan_sha256"):
            errors.append(f"{cid}: capability plan hash differs from generated site manifest")
        page = site / cap_entry["page"]
        if not page.exists():
            errors.append(f"{cid}: missing capability page {page}")
        meta = frontmatter(cap_plans[cid]) if cid in cap_plans else {}
        if cap_entry.get("decision_count") != len(meta.get("decisions", [])):
            errors.append(f"{cid}: decision count mismatch")
        for slice_entry in cap_entry.get("slices", []):
            sid = slice_entry["slice_id"]
            manifest_slices[sid] = slice_entry
            source = repo / slice_entry["plan_path"]
            if not source.exists():
                errors.append(f"{sid}: missing slice plan {source}")
            elif sha256(source) != slice_entry.get("plan_sha256"):
                errors.append(f"{sid}: slice plan hash differs from generated site manifest")
            page = site / slice_entry["page"]
            if not page.exists():
                errors.append(f"{sid}: missing slice page {page}")

    if set(manifest_slices) != set(slice_plans):
        errors.append(f"Manifest slice set differs from plans: {len(manifest_slices)} vs {len(slice_plans)}")

    backlog = yaml.safe_load((repo / "planning/backlog.yaml").read_text(encoding="utf-8"))
    backlog_waves = {str(wave["id"]): wave for wave in backlog.get("waves", [])}
    backlog_slices = {
        str(slice_["id"]): slice_
        for capability in backlog.get("capabilities", [])
        for slice_ in capability.get("slices", [])
    }
    manifest_waves = {str(entry["wave_id"]): entry for entry in manifest.get("waves", [])}
    if set(manifest_waves) != set(backlog_waves):
        errors.append(
            f"Manifest wave set differs from backlog: manifest={sorted(manifest_waves)} backlog={sorted(backlog_waves)}"
        )
    assigned_slice_ids: list[str] = []
    for wave_id, _wave in backlog_waves.items():
        entry = manifest_waves.get(wave_id)
        if entry is None:
            continue
        expected_slice_ids = [slice_id for slice_id, slice_ in backlog_slices.items() if slice_.get("wave") == wave_id]
        actual_slice_ids = [str(slice_id) for slice_id in entry.get("slice_ids", [])]
        assigned_slice_ids.extend(actual_slice_ids)
        if actual_slice_ids != expected_slice_ids:
            errors.append(f"{wave_id}: wave slice inventory differs from authoritative backlog order")
        if entry.get("slice_count") != len(expected_slice_ids):
            errors.append(f"{wave_id}: wave slice count mismatch")
        page = site / str(entry.get("page"))
        if not page.exists():
            errors.append(f"{wave_id}: missing wave page {page}")
        exit_gate = next(
            (gate for gate in backlog.get("release_gates", []) if gate.get("after_wave") == wave_id),
            None,
        )
        if entry.get("exit_gate_id") != (exit_gate or {}).get("id"):
            errors.append(f"{wave_id}: exit gate differs from authoritative backlog")
    duplicate_assignments = sorted(slice_id for slice_id, count in Counter(assigned_slice_ids).items() if count != 1)
    if set(assigned_slice_ids) != set(backlog_slices) or duplicate_assignments:
        errors.append(f"Every backlog slice must appear in exactly one wave page; duplicates={duplicate_assignments}")

    html_pages = sorted(site.rglob("*.html"))
    expected_html = 1 + len(backlog_waves) + len(cap_plans) + len(slice_plans)
    if len(html_pages) != expected_html:
        errors.append(f"Expected {expected_html} HTML pages, found {len(html_pages)}")

    for page in html_pages:
        text = page.read_text(encoding="utf-8")
        parsed = PageParser()
        parsed.feed(text)
        rel = page.relative_to(site).as_posix()
        if parsed.html_lang != "en":
            errors.append(f"{rel}: missing lang=en")
        if parsed.title_count != 1:
            errors.append(f"{rel}: expected one title element, found {parsed.title_count}")
        if parsed.h1_count != 1:
            errors.append(f"{rel}: expected one h1, found {parsed.h1_count}")
        duplicates = sorted({item for item in parsed.ids if parsed.ids.count(item) > 1})
        if duplicates:
            errors.append(f"{rel}: duplicate ids {duplicates}")
        if not any(value.endswith("assets/review.css") for value in parsed.styles):
            errors.append(f"{rel}: missing shared review.css")
        if not any(value.endswith("assets/review.js") for value in parsed.scripts):
            errors.append(f"{rel}: missing shared review.js")
        if parsed.planning_nav_count != 1:
            errors.append(f"{rel}: expected one tabbed planning navigation, found {parsed.planning_nav_count}")
        if parsed.planning_tab_names != ["capabilities", "waves"]:
            errors.append(f"{rel}: planning tabs must be Capabilities then Waves")
        if parsed.planning_panel_names != ["capabilities", "waves"]:
            errors.append(f"{rel}: planning tab panels must match the two planning tabs")
        for href in parsed.hrefs + parsed.styles + parsed.scripts:
            target = local_target(page, href)
            if target is not None and not target.exists():
                errors.append(f"{rel}: broken local reference {href}")
        if page.parent.name == "waves":
            wave_id = page.stem
            if wave_id not in backlog_waves:
                errors.append(f"{rel}: wave page has no matching backlog wave")
            content = " ".join(parsed.text_parts)
            if "Capability increments and ordered slices" not in content:
                errors.append(f"{rel}: missing wave capability-increment breakdown")
            if "Wave exit / successor activation" not in content:
                errors.append(f"{rel}: missing wave gate-decision breakdown")
        elif page.name == "index.html" and page.parent.name in cap_plans:
            cid = page.parent.name
            meta = frontmatter(cap_plans[cid])
            expected = {decision["id"] for decision in meta.get("decisions", [])}
            actual = set(parsed.decision_ids)
            if expected != actual:
                errors.append(f"{rel}: rendered decision IDs differ from capability plan")
            if "Resolved capability decisions and wave approval" not in " ".join(parsed.text_parts):
                errors.append(f"{rel}: missing resolved-decision/wave-approval surface")
            decision_count = len(expected)
            if parsed.other_choice_count != decision_count:
                errors.append(f"{rel}: expected {decision_count} Other choices, found {parsed.other_choice_count}")
            if parsed.other_input_count != decision_count:
                errors.append(
                    f"{rel}: expected {decision_count} Other-description inputs, found {parsed.other_input_count}"
                )
            if parsed.rationale_count != decision_count:
                errors.append(
                    f"{rel}: expected {decision_count} detailed-rationale fields, found {parsed.rationale_count}"
                )
        elif page.parent.name in cap_plans:
            sid = page.stem
            if sid not in slice_plans:
                errors.append(f"{rel}: slice page has no matching source plan")
            content = " ".join(parsed.text_parts)
            if "Capability decision gate" not in content:
                errors.append(f"{rel}: missing capability decision gate near top")
            if "Recommended implementation selections" not in content:
                warnings.append(f"{rel}: slice decision summary heading not found")

    for required in [site / "assets/review.css", site / "assets/review.js", site / "README.md"]:
        if not required.exists():
            errors.append(f"Missing required review-site artifact: {required}")

    review_js = site / "assets/review.js"
    if review_js.exists():
        js_text = review_js.read_text(encoding="utf-8")
        for marker in (
            'const otherSentinel = "__OTHER__"',
            'schema_version: "1.1"',
            "other_option",
            'navigation.querySelectorAll("[data-nav-tab]")',
            'event.key === "ArrowRight"',
        ):
            if marker not in js_text:
                errors.append(f"assets/review.js: missing Other-feedback marker {marker}")

    result = {
        "schema_version": "1.0",
        "site": str(site),
        "capability_count": len(cap_plans),
        "slice_count": len(slice_plans),
        "html_page_count": len(html_pages),
        "errors": errors,
        "warnings": warnings,
        "status": "pass" if not errors else "fail",
    }
    if args.report:
        report = Path(args.report)
        if not report.is_absolute():
            report = repo / report
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    print(
        f"Planning review site: {result['status']} - {len(cap_plans)} capabilities, "
        f"{len(slice_plans)} slices, {len(html_pages)} HTML pages"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
