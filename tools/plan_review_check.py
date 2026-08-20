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

    ecr_packets = {
        path.name.removesuffix(".packet.json"): path
        for path in (repo / "planning/enabler-change-requests").glob("ECR-*.packet.json")
    }
    manifest_ecrs: dict[str, dict[str, Any]] = {}
    for entry in manifest.get("enabler_change_requests", []):
        change_id = str(entry.get("change_request_id"))
        if change_id in manifest_ecrs:
            errors.append(f"Duplicate enabler change request in manifest: {change_id}")
        manifest_ecrs[change_id] = entry
    if set(manifest_ecrs) != set(ecr_packets):
        errors.append(
            f"Manifest ECR set differs from packets: manifest={sorted(manifest_ecrs)} packets={sorted(ecr_packets)}"
        )
    for change_id, packet_path in ecr_packets.items():
        entry = manifest_ecrs.get(change_id)
        if entry is None:
            continue
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        expected_packet_path = packet_path.relative_to(repo).as_posix()
        if entry.get("packet_path") != expected_packet_path or entry.get("packet_sha256") != sha256(packet_path):
            errors.append(f"{change_id}: packet path/hash differs from generated site manifest")
        declared = {str(item.get("role")): item for item in packet.get("files", [])}
        for role, path_key, hash_key in (
            ("canonical-proposal", "proposal_path", "proposal_sha256"),
            ("human-review", "review_path", "review_sha256"),
        ):
            source_record = declared.get(role) or {}
            source_path = repo / str(source_record.get("path") or "")
            if not source_path.exists():
                errors.append(f"{change_id}: missing declared {role} source {source_path}")
            elif (
                entry.get(path_key) != source_record.get("path")
                or entry.get(hash_key) != source_record.get("sha256")
                or sha256(source_path) != source_record.get("sha256")
            ):
                errors.append(f"{change_id}: {role} path/hash differs from packet or source bytes")
        approval_path_value = entry.get("approval_path")
        if approval_path_value:
            approval_path = repo / str(approval_path_value)
            if not approval_path.exists() or entry.get("approval_sha256") != sha256(approval_path):
                errors.append(f"{change_id}: approval path/hash differs from source bytes")
            else:
                approval = json.loads(approval_path.read_text(encoding="utf-8"))
                approved_packet = approval.get("packet") or {}
                if approved_packet.get("path") != expected_packet_path or approved_packet.get("sha256") != sha256(
                    packet_path
                ):
                    errors.append(f"{change_id}: approval does not bind current packet bytes")
                if entry.get("approval_status") != approval.get("status"):
                    errors.append(f"{change_id}: approval status differs from source record")
        page = site / str(entry.get("page"))
        if not page.exists():
            errors.append(f"{change_id}: missing enabler detail page {page}")

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
    backlog_capabilities = {str(capability["id"]): capability for capability in backlog.get("capabilities", [])}
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
        expected_capability_ids = [
            capability_id
            for capability_id, capability in backlog_capabilities.items()
            if any(slice_.get("wave") == wave_id for slice_ in capability.get("slices", []))
        ]
        expected_decision_ids = [
            str(decision["id"])
            for capability_id in expected_capability_ids
            if capability_id in cap_plans
            for decision in frontmatter(cap_plans[capability_id]).get("decisions", [])
            if wave_id in decision.get("binding_waves", [])
        ]
        actual_slice_ids = [str(slice_id) for slice_id in entry.get("slice_ids", [])]
        assigned_slice_ids.extend(actual_slice_ids)
        if [str(capability_id) for capability_id in entry.get("capability_ids", [])] != expected_capability_ids:
            errors.append(f"{wave_id}: wave capability inventory differs from authoritative backlog order")
        if [str(decision_id) for decision_id in entry.get("decision_ids", [])] != expected_decision_ids:
            errors.append(f"{wave_id}: wave binding-decision inventory differs from capability plans")
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
        if entry.get("approval_status") != (backlog_waves[wave_id].get("approval") or {}).get("status"):
            errors.append(f"{wave_id}: pre-Wave approval status differs from authoritative backlog")
        if entry.get("completion_status") != (backlog_waves[wave_id].get("completion") or {}).get("status"):
            errors.append(f"{wave_id}: Wave completion status differs from authoritative backlog")
        expected_interruptions = [
            change_id
            for change_id, ecr in manifest_ecrs.items()
            if ecr.get("target_wave") == wave_id
            and ecr.get("approval_status") == "APPROVED"
            and ecr.get("lifecycle_status") not in {"ADOPTED", "DEFERRED", "WITHDRAWN"}
            and (
                ecr.get("lifecycle_status") != "NOT_MATERIALIZED"
                or (
                    ((backlog_waves[wave_id].get("campaign") or {}).get("status") == "PAUSED")
                    and ecr.get("classification") == "gate-integrity-safety-defect"
                )
            )
        ]
        if entry.get("interrupting_change_request_ids", []) != expected_interruptions:
            errors.append(f"{wave_id}: interrupting ECR inventory differs from source authority")
    duplicate_assignments = sorted(slice_id for slice_id, count in Counter(assigned_slice_ids).items() if count != 1)
    if set(assigned_slice_ids) != set(backlog_slices) or duplicate_assignments:
        errors.append(f"Every backlog slice must appear in exactly one wave page; duplicates={duplicate_assignments}")

    html_pages = sorted(site.rglob("*.html"))
    expected_html = 2 + len(ecr_packets) + len(backlog_waves) + len(cap_plans) + len(slice_plans)
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
            if "Complete pre-Wave approval packet" not in content:
                errors.append(f"{rel}: missing complete pre-Wave approval surface")
            if "Approval covers exactly" not in content or "Binding in this Wave" not in content:
                errors.append(f"{rel}: missing exact Wave-binding approval boundary")
            if "Inherited and future decisions are context only" not in content:
                errors.append(f"{rel}: missing nonbinding decision-context boundary")
            if "Capability contributions and ordered slices" not in content:
                errors.append(f"{rel}: missing Wave capability-contribution breakdown")
            if "Review and verification cadence while the Wave runs" not in content:
                errors.append(f"{rel}: missing Wave review/testing cadence")
            if "Wave exit / successor activation" not in content:
                errors.append(f"{rel}: missing wave gate-decision breakdown")
            approval_status = (backlog_waves.get(wave_id, {}).get("approval") or {}).get("status")
            approval_command = f"wave approve {wave_id}"
            if approval_status == "APPROVED":
                if "Immutable authority" not in content:
                    errors.append(f"{rel}: approved Wave must show immutable authority guidance")
                if approval_command in text:
                    errors.append(f"{rel}: approved Wave advertises repeated approval")
            elif approval_command not in text:
                errors.append(f"{rel}: pending Wave is missing its approval instruction")
            if (manifest_waves.get(wave_id) or {}).get("interrupting_change_request_ids"):
                for marker in (
                    "ordinary execution is interrupted",
                    "Legal alternatives",
                    "Exact ordinary resume condition",
                ):
                    if marker not in content:
                        errors.append(f"{rel}: interrupted Wave is missing stopped-amendment marker {marker}")
                if f"wave start {wave_id}" in text or f"wave approve {wave_id}" in text:
                    errors.append(f"{rel}: interrupted Wave advertises start or repeated approval")
        elif page.parent.name == "enablers":
            content = " ".join(parsed.text_parts)
            if page.name == "index.html":
                if "Enabler change request register" not in content:
                    errors.append(f"{rel}: missing ECR register heading")
            else:
                change_id = page.stem
                if change_id not in ecr_packets:
                    errors.append(f"{rel}: enabler page has no matching packet")
                for marker in (
                    "Proposal, approval, materialization, and campaign state",
                    "Hash-bound source records",
                    "Ordered Wave authority chain",
                    "Safe resume boundary",
                ):
                    if marker not in content:
                        errors.append(f"{rel}: missing ECR detail marker {marker}")
        elif page.name == "index.html" and page.parent.name in cap_plans:
            cid = page.parent.name
            meta = frontmatter(cap_plans[cid])
            expected = {decision["id"] for decision in meta.get("decisions", [])}
            actual = set(parsed.decision_ids)
            if expected != actual:
                errors.append(f"{rel}: rendered decision IDs differ from capability plan")
            if "Capability decisions classified by Wave approval" not in " ".join(parsed.text_parts):
                errors.append(f"{rel}: missing Wave-classified decision surface")
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

    for required in [
        site / "assets/review.css",
        site / "assets/review.js",
        site / "enablers/index.html",
        site / "README.md",
    ]:
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
