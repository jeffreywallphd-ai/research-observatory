#!/usr/bin/env python3
"""Validate the generated static capability/slice planning review site."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import tempfile
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml
from plan_review_site import build_site, extract_task_section


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


def markdown_body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    end = text.find("\n---\n", 4)
    if not text.startswith("---\n") or end < 0:
        raise ValueError(f"{path}: invalid YAML front matter")
    return text[end + 5 :]


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def generated_site_byte_errors(repo: Path, site: Path) -> list[str]:
    """Prove that reviewer-visible files are the exact deterministic projection."""
    manifest_path = site / "manifest.json"
    if not manifest_path.is_file():
        return ["Cannot regenerate the review site without its manifest"]
    with tempfile.TemporaryDirectory() as temporary:
        expected = Path(temporary) / "review-site"
        expected.mkdir(parents=True)
        # build_site deliberately retains an existing generated_at value. Seed only
        # that governed manifest so the comparison is content-exact and timestamp-stable.
        (expected / "manifest.json").write_bytes(manifest_path.read_bytes())
        build_site(repo, expected)
        actual_files = {path.relative_to(site).as_posix(): path for path in site.rglob("*") if path.is_file()}
        expected_files = {path.relative_to(expected).as_posix(): path for path in expected.rglob("*") if path.is_file()}
        errors: list[str] = []
        if set(actual_files) != set(expected_files):
            missing = sorted(set(expected_files) - set(actual_files))
            extra = sorted(set(actual_files) - set(expected_files))
            errors.append(
                "Generated review-site file inventory differs from deterministic regeneration: "
                f"missing={missing[:1]} extra={extra[:1]}"
            )
        for relative in sorted(set(actual_files) & set(expected_files)):
            if actual_files[relative].read_bytes() != expected_files[relative].read_bytes():
                errors.append(f"{relative}: visible content differs from deterministic regeneration")
        return errors


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
        self.page_type: str | None = None
        self.wave_capability_ids: list[str] = []
        self.wave_slice_ids: list[str] = []
        self.wave_task_ids: list[str] = []
        self.html_lang: str | None = None
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value for key, value in attrs}
        if tag == "html":
            self.html_lang = values.get("lang")
        if tag == "body":
            self.page_type = values.get("data-page-type")
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
        if values.get("data-wave-capability"):
            self.wave_capability_ids.append(values["data-wave-capability"] or "")
        if values.get("data-wave-slice"):
            self.wave_slice_ids.append(values["data-wave-slice"] or "")
        if values.get("data-wave-task"):
            self.wave_task_ids.append(values["data-wave-task"] or "")
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


def task_review_projection(task: dict[str, Any]) -> dict[str, Any]:
    control = task.get("review_control")
    return {
        "task_id": task.get("id"),
        "title": task.get("title"),
        "status": task.get("status"),
        "mode": "append-only" if isinstance(control, dict) else "latest-review-only",
        "latest_review": task.get("review") or {},
        "review_control": control if isinstance(control, dict) else None,
    }


def amendment_exit_projection(amendment: dict[str, Any]) -> dict[str, Any]:
    completion = amendment.get("completion") or {}
    control = completion.get("exit_review_control")
    return {
        "amendment_id": amendment.get("id"),
        "mode": "append-only" if isinstance(control, dict) else "latest-completion-only",
        "latest_completion": {
            key: completion.get(key) for key in ("status", "reviewer", "reviewed_at", "evidence", "notes")
        },
        "exit_review_control": control if isinstance(control, dict) else None,
    }


def amendment_adoption_checkpoints(amendment: dict[str, Any], waves: list[dict[str, Any]]) -> list[dict[str, Any]]:
    target_wave = amendment.get("target_wave")
    wave = next((item for item in waves if item.get("id") == target_wave), {})
    projections: list[dict[str, Any]] = []
    for checkpoint in wave.get("checkpoints") or []:
        references = [
            reference
            for reference in checkpoint.get("evidence") or []
            if isinstance(reference, dict)
            and reference.get("type") == "amendment-adoption-evidence"
            and reference.get("amendment_id") == amendment.get("id")
        ]
        if references:
            projections.append(
                {
                    "id": checkpoint.get("id"),
                    "kind": checkpoint.get("kind"),
                    "recorded_by": checkpoint.get("recorded_by"),
                    "recorded_at": checkpoint.get("recorded_at"),
                    "notes": checkpoint.get("notes"),
                    "evidence_references": references,
                }
            )
    return projections


def amendment_exit_manifest_errors(
    label: str,
    manifest_projection: Any,
    manifest_checkpoints: Any,
    amendment: dict[str, Any],
    waves: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    if manifest_projection != amendment_exit_projection(amendment):
        errors.append(f"{label}: amendment-exit history/current projection differs from authoritative backlog")
    if manifest_checkpoints != amendment_adoption_checkpoints(amendment, waves):
        errors.append(f"{label}: amendment-adoption checkpoint references differ from authoritative backlog")
    return errors


def amendment_exit_render_errors(
    text: str,
    projection: dict[str, Any],
    adoption_checkpoints: list[dict[str, Any]],
) -> list[str]:
    amendment_id = str(projection.get("amendment_id"))
    amendment_attr = html.escape(amendment_id, quote=True)
    mode = str(projection.get("mode"))
    errors: list[str] = []
    if text.count(f'data-amendment-exit-id="{amendment_attr}"') != 1:
        errors.append(f"{amendment_id}: rendered amendment-exit identity is missing or duplicated")
    if f'data-exit-review-mode="{html.escape(mode, quote=True)}"' not in text:
        errors.append(f"{amendment_id}: rendered amendment-exit mode differs from authoritative completion")

    latest = projection.get("latest_completion") or {}
    if f'data-latest-completion-projection="{amendment_attr}"' not in text:
        errors.append(f"{amendment_id}: latest completion projection is missing")
    for attribute, value in (
        ("data-latest-completion-status", latest.get("status") or "PENDING"),
        ("data-latest-completion-reviewer", latest.get("reviewer") or "none"),
        ("data-latest-completion-reviewed-at", latest.get("reviewed_at") or "none"),
        ("data-latest-completion-notes", latest.get("notes") or "none"),
    ):
        if f'{attribute}="{html.escape(str(value), quote=True)}"' not in text:
            errors.append(f"{amendment_id}: latest completion projection differs at {attribute}")
    completion_evidence_prefix = f'data-latest-completion-evidence="{amendment_attr}:'
    latest_evidence = latest.get("evidence") or []
    if text.count(completion_evidence_prefix) != len(latest_evidence):
        errors.append(f"{amendment_id}: latest completion evidence count differs from authoritative completion")
    for index, reference in enumerate(latest_evidence, start=1):
        marker = f'{completion_evidence_prefix}{index}">{html.escape(str(reference))}</code>'
        if marker not in text:
            errors.append(f"{amendment_id}: latest completion evidence reference {index} is missing or altered")

    attempt_prefix = f'data-exit-review-attempt="{amendment_attr}:'
    finding_prefix = f'data-exit-review-finding="{amendment_attr}:'
    closure_prefix = f'data-exit-review-closure="{amendment_attr}:'
    current_prefix = f'data-exit-current-submission="{amendment_attr}:'
    control = projection.get("exit_review_control")
    if not isinstance(control, dict):
        for item_label, prefix in (
            ("attempt", attempt_prefix),
            ("finding", finding_prefix),
            ("closure", closure_prefix),
            ("current submission", current_prefix),
        ):
            if prefix in text:
                errors.append(f"{amendment_id}: legacy latest-completion-only record fabricates a {item_label}")
    else:
        attempts = control.get("attempts") or []
        expected_findings = sum(len(attempt.get("findings") or []) for attempt in attempts)
        expected_closures = sum(len(attempt.get("closures") or []) for attempt in attempts)
        if text.count(attempt_prefix) != len(attempts):
            errors.append(f"{amendment_id}: rendered amendment-exit round count differs from history")
        if text.count(finding_prefix) != expected_findings:
            errors.append(f"{amendment_id}: rendered amendment-exit finding count differs from history")
        if text.count(closure_prefix) != expected_closures:
            errors.append(f"{amendment_id}: rendered amendment-exit closure count differs from history")
        for attempt in attempts:
            packet = attempt.get("submission") or {}
            attempt_id = str(packet.get("id"))
            attempt_attr = html.escape(attempt_id, quote=True)
            packet_hash = html.escape(str(packet.get("packet_sha256")), quote=True)
            review = attempt.get("review") or {}
            ledger = attempt.get("ledger") or {}
            if (
                f'data-exit-review-attempt="{amendment_attr}:{attempt_attr}"' not in text
                or f'data-exit-packet-sha256="{packet_hash}"' not in text
            ):
                errors.append(f"{amendment_id}: exit round {attempt_id} packet identity/hash is missing")
            if (
                f'data-exit-review-round="{amendment_attr}:{attempt_attr}"' not in text
                or f'data-reviewed-state-commit="{html.escape(str(review.get("reviewed_state_commit")), quote=True)}"'
                not in text
            ):
                errors.append(f"{amendment_id}: exit round {attempt_id} reviewed-state binding is missing")
            if (
                f'data-exit-review-ledger="{amendment_attr}:{attempt_attr}"' not in text
                or f'data-exit-ledger-sha256="{html.escape(str(ledger.get("sha256")), quote=True)}"' not in text
            ):
                errors.append(f"{amendment_id}: exit round {attempt_id} ledger identity/hash is missing")
            evidence = packet.get("evidence_reference") or {}
            for attribute, value in (
                ("data-exit-evidence-amendment", evidence.get("amendment_id")),
                ("data-exit-evidence-path", evidence.get("path")),
                ("data-exit-evidence-sha256", evidence.get("sha256")),
                ("data-exit-evidence-commit", evidence.get("commit")),
            ):
                if f'{attribute}="{html.escape(str(value), quote=True)}"' not in text:
                    errors.append(f"{amendment_id}: exit round {attempt_id} differs at {attribute}")
            for item_label, value in (
                ("evidence amendment", evidence.get("amendment_id")),
                ("evidence path", evidence.get("path")),
                ("evidence hash", evidence.get("sha256")),
                ("evidence commit", evidence.get("commit")),
                ("criteria hash", packet.get("acceptance_criteria_sha256")),
                ("selected-check hash", packet.get("selected_checks_sha256")),
            ):
                if f">{html.escape(str(value))}<" not in text:
                    errors.append(f"{amendment_id}: exit round {attempt_id} {item_label} is missing")
            for finding in attempt.get("findings") or []:
                marker = f"{amendment_attr}:{attempt_attr}:{html.escape(str(finding.get('id')), quote=True)}"
                if f'data-exit-review-finding="{marker}"' not in text:
                    errors.append(f"{amendment_id}: exit finding {finding.get('id')} is missing from {attempt_id}")
            for closure in attempt.get("closures") or []:
                marker = f"{amendment_attr}:{attempt_attr}:{html.escape(str(closure.get('finding_id')), quote=True)}"
                if f'data-exit-review-closure="{marker}"' not in text:
                    errors.append(
                        f"{amendment_id}: exit closure {closure.get('finding_id')} is missing from {attempt_id}"
                    )
        current = control.get("current_submission")
        if isinstance(current, dict):
            marker = f"{amendment_attr}:{html.escape(str(current.get('id')), quote=True)}"
            if (
                text.count(current_prefix) != 1
                or f'data-exit-current-submission="{marker}"' not in text
                or f'data-exit-packet-sha256="{html.escape(str(current.get("packet_sha256")), quote=True)}"' not in text
            ):
                errors.append(f"{amendment_id}: current immutable exit submission identity/hash is missing")
            current_evidence = current.get("evidence_reference") or {}
            for attribute, value in (
                ("data-exit-evidence-amendment", current_evidence.get("amendment_id")),
                ("data-exit-evidence-path", current_evidence.get("path")),
                ("data-exit-evidence-sha256", current_evidence.get("sha256")),
                ("data-exit-evidence-commit", current_evidence.get("commit")),
            ):
                if f'{attribute}="{html.escape(str(value), quote=True)}"' not in text:
                    errors.append(f"{amendment_id}: current immutable exit submission differs at {attribute}")
        elif current_prefix in text:
            errors.append(f"{amendment_id}: rendered exit history invents a current submission")

    checkpoint_prefix = f'data-adoption-checkpoint="{amendment_attr}:'
    evidence_prefix = f'data-adoption-evidence="{amendment_attr}:'
    expected_references = sum(len(item.get("evidence_references") or []) for item in adoption_checkpoints)
    if text.count(checkpoint_prefix) != len(adoption_checkpoints):
        errors.append(f"{amendment_id}: adoption checkpoint count differs from authoritative Wave")
    if text.count(evidence_prefix) != expected_references:
        errors.append(f"{amendment_id}: adoption evidence-reference count differs from authoritative Wave")
    for checkpoint in adoption_checkpoints:
        checkpoint_id = html.escape(str(checkpoint.get("id")), quote=True)
        if f'data-adoption-checkpoint="{amendment_attr}:{checkpoint_id}"' not in text:
            errors.append(f"{amendment_id}: adoption checkpoint {checkpoint.get('id')} is missing")
        for index, reference in enumerate(checkpoint.get("evidence_references") or [], start=1):
            marker = f"{amendment_attr}:{checkpoint_id}:{index}"
            if (
                f'data-adoption-evidence="{marker}"' not in text
                or f'data-adoption-evidence-amendment="{html.escape(str(reference.get("amendment_id")), quote=True)}"'
                not in text
                or f'data-adoption-evidence-sha256="{html.escape(str(reference.get("sha256")), quote=True)}"'
                not in text
                or f'data-adoption-evidence-commit="{html.escape(str(reference.get("commit")), quote=True)}"'
                not in text
                or f">{html.escape(str(reference.get('path')))}<" not in text
            ):
                errors.append(
                    f"{amendment_id}: adoption checkpoint {checkpoint.get('id')} "
                    f"reference {index} is missing or altered"
                )
    return errors


def task_review_manifest_errors(
    label: str,
    manifest_reviews: Any,
    tasks: list[dict[str, Any]],
) -> list[str]:
    expected = [task_review_projection(task) for task in tasks]
    if manifest_reviews == expected:
        return []
    return [f"{label}: task review histories differ from authoritative backlog"]


def task_review_render_errors(text: str, projection: dict[str, Any]) -> list[str]:
    task_id = str(projection.get("task_id"))
    mode = str(projection.get("mode"))
    task_attr = html.escape(task_id, quote=True)
    errors: list[str] = []
    if text.count(f'data-task-review-id="{task_attr}"') != 1:
        errors.append(f"{task_id}: rendered task review identity is missing or duplicated")
    if f'data-review-mode="{html.escape(mode, quote=True)}"' not in text:
        errors.append(f"{task_id}: rendered review mode differs from authoritative task")
    latest = projection.get("latest_review") or {}
    projection_marker = f'data-current-review-projection="{task_attr}"'
    if projection_marker not in text:
        errors.append(f"{task_id}: current latest-review projection is missing")
    for attribute, value in (
        ("data-current-review-result", latest.get("result") or "not-reviewed"),
        ("data-current-reviewer", latest.get("reviewer") or "none"),
        ("data-current-reviewed-at", latest.get("reviewed_at") or "none"),
    ):
        if f'{attribute}="{html.escape(str(value), quote=True)}"' not in text:
            errors.append(f"{task_id}: current latest-review projection differs at {attribute}")

    attempt_prefix = f'data-review-attempt="{task_attr}:'
    finding_prefix = f'data-review-finding="{task_attr}:'
    closure_prefix = f'data-review-closure="{task_attr}:'
    current_prefix = f'data-current-submission="{task_attr}:'
    control = projection.get("review_control")
    if not isinstance(control, dict):
        for label, prefix in (
            ("attempt", attempt_prefix),
            ("finding", finding_prefix),
            ("closure", closure_prefix),
            ("current submission", current_prefix),
        ):
            if prefix in text:
                errors.append(f"{task_id}: legacy latest-review-only task fabricates a {label}")
        return errors

    attempts = control.get("attempts") or []
    expected_findings = sum(len(attempt.get("findings") or []) for attempt in attempts)
    expected_closures = sum(len(attempt.get("closures") or []) for attempt in attempts)
    if text.count(attempt_prefix) != len(attempts):
        errors.append(f"{task_id}: rendered review round count differs from append-only history")
    if text.count(finding_prefix) != expected_findings:
        errors.append(f"{task_id}: rendered finding count differs from append-only history")
    if text.count(closure_prefix) != expected_closures:
        errors.append(f"{task_id}: rendered closure count differs from append-only history")
    for attempt in attempts:
        packet = attempt.get("submission") or {}
        attempt_id = str(packet.get("id"))
        packet_hash = str(packet.get("packet_sha256"))
        ledger = attempt.get("ledger") or {}
        if (
            f'data-review-attempt="{task_attr}:{html.escape(attempt_id, quote=True)}"' not in text
            or f'data-packet-sha256="{html.escape(packet_hash, quote=True)}"' not in text
        ):
            errors.append(f"{task_id}: review round {attempt_id} packet identity/hash is missing")
        if (
            f'data-review-ledger="{task_attr}:{html.escape(attempt_id, quote=True)}"' not in text
            or f'data-ledger-sha256="{html.escape(str(ledger.get("sha256")), quote=True)}"' not in text
        ):
            errors.append(f"{task_id}: review round {attempt_id} ledger identity/hash is missing")
        evidence = packet.get("evidence_reference") or {}
        for label, value in (
            ("evidence hash", evidence.get("sha256")),
            ("criteria hash", packet.get("acceptance_criteria_sha256")),
            ("selection hash", packet.get("selection_sha256")),
        ):
            if f">{html.escape(str(value))}<" not in text:
                errors.append(f"{task_id}: review round {attempt_id} {label} is missing")
        for finding in attempt.get("findings") or []:
            marker = (
                f"{task_attr}:{html.escape(attempt_id, quote=True)}:{html.escape(str(finding.get('id')), quote=True)}"
            )
            if f'data-review-finding="{marker}"' not in text:
                errors.append(f"{task_id}: finding {finding.get('id')} is missing from round {attempt_id}")
        for closure in attempt.get("closures") or []:
            closure_id = html.escape(str(closure.get("finding_id")), quote=True)
            marker = f"{task_attr}:{html.escape(attempt_id, quote=True)}:{closure_id}"
            if f'data-review-closure="{marker}"' not in text:
                errors.append(f"{task_id}: closure {closure.get('finding_id')} is missing from round {attempt_id}")

    current = control.get("current_submission")
    if isinstance(current, dict):
        marker = f"{task_attr}:{html.escape(str(current.get('id')), quote=True)}"
        if (
            text.count(current_prefix) != 1
            or f'data-current-submission="{marker}"' not in text
            or f'data-packet-sha256="{html.escape(str(current.get("packet_sha256")), quote=True)}"' not in text
        ):
            errors.append(f"{task_id}: current immutable submission identity/hash is missing")
    elif current_prefix in text:
        errors.append(f"{task_id}: rendered history invents a current submission")
    return errors


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

    errors.extend(generated_site_byte_errors(repo, site))

    cap_plans = {path.stem: path for path in (repo / "planning/capability-plans").glob("CAP-*.md")}
    slice_plans: dict[str, Path] = {}
    for path in (repo / "planning/slice-plans").glob("CAP-*/*.md"):
        meta = frontmatter(path)
        slice_plans[meta["slice_id"]] = path

    backlog = yaml.safe_load((repo / "planning/backlog.yaml").read_text(encoding="utf-8"))
    backlog_slices = {
        str(slice_["id"]): slice_
        for capability in backlog.get("capabilities", [])
        for slice_ in capability.get("slices", [])
    }
    backlog_tasks = {
        str(task["id"]): task
        for slice_id, slice_ in backlog_slices.items()
        if slice_id in slice_plans and slice_id.split(".")[0] in cap_plans
        for task in slice_.get("tasks", [])
    }
    amendments_by_change = {
        str(amendment.get("change_request_id")): amendment
        for amendment in backlog.get("wave_amendments", [])
        if amendment.get("change_request_id")
    }
    waves = backlog.get("waves") or []
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
        bootstrap_id = str((packet.get("bootstrapUnit") or {}).get("id") or "")
        expected_addenda = {
            path.relative_to(repo).as_posix(): path
            for path in (repo / "planning/wave-amendment-approvals").glob(f"{bootstrap_id}.addendum-*.json")
        }
        manifest_addenda = {
            str(item.get("path")): item for item in entry.get("scope_addenda", []) if isinstance(item, dict)
        }
        if set(expected_addenda) != set(manifest_addenda):
            errors.append(f"{change_id}: bootstrap scope-addendum set differs from source records")
        for relative, addendum_path in expected_addenda.items():
            addendum = json.loads(addendum_path.read_text(encoding="utf-8"))
            manifest_addendum = manifest_addenda.get(relative) or {}
            if manifest_addendum.get("sha256") != sha256(addendum_path):
                errors.append(f"{change_id}: bootstrap scope-addendum hash differs from source bytes")
            if (
                addendum.get("status") != "APPROVED"
                or addendum.get("amendmentId") != packet.get("proposedAmendmentId")
                or addendum.get("bootstrapUnit") != bootstrap_id
            ):
                errors.append(f"{change_id}: bootstrap scope-addendum identity/status mismatch")
        source_bootstrap = (amendments_by_change.get(change_id) or {}).get("bootstrap") or {}
        expected_attempts = [dict(item) for item in source_bootstrap.get("attempts", [])]
        if source_bootstrap:
            expected_attempts.append(
                {
                    "id": f"R{len(expected_attempts) + 1:02d}",
                    "implementer": source_bootstrap.get("implementer"),
                    "implementation_commit": source_bootstrap.get("implementation_commit"),
                    "evidence": source_bootstrap.get("evidence") or [],
                    "review": source_bootstrap.get("review") or {},
                    "current_status": source_bootstrap.get("status"),
                }
            )
        if entry.get("bootstrap_attempts") != expected_attempts:
            errors.append(f"{change_id}: bootstrap review attempts differ from authoritative backlog history")
        source_tasks = (amendments_by_change.get(change_id) or {}).get("tasks", [])
        expected_task_reviews = [task_review_projection(task) for task in source_tasks]
        errors.extend(task_review_manifest_errors(change_id, entry.get("task_reviews"), source_tasks))
        source_amendment = amendments_by_change.get(change_id) or {
            "id": packet.get("proposedAmendmentId"),
            "completion": {},
        }
        expected_exit_review = amendment_exit_projection(source_amendment)
        expected_adoption_checkpoints = amendment_adoption_checkpoints(source_amendment, waves)
        errors.extend(
            amendment_exit_manifest_errors(
                change_id,
                entry.get("exit_review"),
                entry.get("adoption_checkpoints"),
                source_amendment,
                waves,
            )
        )
        page = site / str(entry.get("page"))
        if not page.exists():
            errors.append(f"{change_id}: missing enabler detail page {page}")
        else:
            page_text = page.read_text(encoding="utf-8")
            for projection in expected_task_reviews:
                errors.extend(f"{change_id}: {error}" for error in task_review_render_errors(page_text, projection))
            errors.extend(
                f"{change_id}: {error}"
                for error in amendment_exit_render_errors(
                    page_text,
                    expected_exit_review,
                    expected_adoption_checkpoints,
                )
            )

    recovery_holds = {
        str(hold.get("recovery_request_id")): hold
        for hold in (backlog.get("control_plane") or {}).get("recovery_holds", [])
    }
    manifest_recoveries = {str(entry.get("request_id")): entry for entry in manifest.get("governance_recoveries", [])}
    if set(manifest_recoveries) != set(recovery_holds):
        errors.append(
            "Manifest governance recovery set differs from backlog holds: "
            f"manifest={sorted(manifest_recoveries)} holds={sorted(recovery_holds)}"
        )
    for request_id, hold in recovery_holds.items():
        entry = manifest_recoveries.get(request_id)
        if entry is None:
            continue
        packet_reference = hold.get("packet_reference") or {}
        approval_reference = hold.get("approval_reference") or {}
        for label, reference, path_key, hash_key in (
            ("packet", packet_reference, "packet_path", "packet_sha256"),
            ("approval", approval_reference, "approval_path", "approval_sha256"),
        ):
            source = repo / str(reference.get("path") or "")
            if not source.exists() or sha256(source) != reference.get("sha256"):
                errors.append(f"{request_id}: recovery {label} source hash mismatch")
            if entry.get(path_key) != reference.get("path") or entry.get(hash_key) != reference.get("sha256"):
                errors.append(f"{request_id}: recovery {label} manifest binding mismatch")
        if (
            entry.get("hold_id") != hold.get("id")
            or entry.get("target_wave") != hold.get("target_wave")
            or entry.get("hold_status") != hold.get("status")
            or entry.get("bootstrap_id") != (hold.get("bootstrap") or {}).get("id")
            or entry.get("bootstrap_status") != (hold.get("bootstrap") or {}).get("status")
            or entry.get("release_conditions") != hold.get("release_conditions")
        ):
            errors.append(f"{request_id}: recovery manifest state differs from the authoritative hold")
        expected_supplements = [
            {
                "id": item.get("id"),
                "bootstrap_id": (item.get("bootstrap") or {}).get("id"),
                "bootstrap_status": (item.get("bootstrap") or {}).get("status"),
                "packet_path": (item.get("packet_reference") or {}).get("path"),
                "packet_sha256": (item.get("packet_reference") or {}).get("sha256"),
                "packet_commit": (item.get("packet_reference") or {}).get("commit"),
                "approval_path": (item.get("approval_reference") or {}).get("path"),
                "approval_sha256": (item.get("approval_reference") or {}).get("sha256"),
                "approval_commit": (item.get("approval_reference") or {}).get("introduction_commit"),
            }
            for item in hold.get("supplements", [])
        ]
        if entry.get("supplements", []) != expected_supplements:
            errors.append(f"{request_id}: recovery supplement manifest differs from the append-only hold ledger")
        page = site / str(entry.get("page") or "")
        if not page.exists():
            errors.append(f"{request_id}: missing governance recovery detail page")

    manifest_caps = {entry["capability_id"]: entry for entry in manifest.get("capabilities", [])}
    if set(manifest_caps) != set(cap_plans):
        errors.append(
            f"Manifest capability set differs from plans: manifest={sorted(manifest_caps)} plans={sorted(cap_plans)}"
        )

    manifest_slices: dict[str, dict[str, Any]] = {}
    manifest_tasks: dict[str, dict[str, Any]] = {}
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
                continue
            source_tasks = (backlog_slices.get(str(sid)) or {}).get("tasks", [])
            source_body = markdown_body(source)
            errors.extend(task_review_manifest_errors(str(sid), slice_entry.get("task_reviews"), source_tasks))
            expected_task_ids = [str(task["id"]) for task in source_tasks]
            task_entries = slice_entry.get("tasks", [])
            actual_task_ids = [str(task_entry.get("task_id")) for task_entry in task_entries]
            if actual_task_ids != expected_task_ids:
                errors.append(f"{sid}: task-page inventory differs from authoritative backlog order")
            source_by_id = {str(task["id"]): task for task in source_tasks}
            for task_entry in task_entries:
                task_id = str(task_entry.get("task_id"))
                if task_id in manifest_tasks:
                    errors.append(f"Duplicate task in manifest: {task_id}")
                    continue
                manifest_tasks[task_id] = task_entry
                source_task = source_by_id.get(task_id)
                if source_task is None:
                    errors.append(f"{sid}: unknown task page inventory entry {task_id}")
                    continue
                expected_page = f"{cid}/{task_id}.html"
                if task_entry.get("page") != expected_page:
                    errors.append(f"{task_id}: task page path is not the canonical task-keyed path")
                if task_entry.get("title") != source_task.get("title") or task_entry.get("status") != source_task.get(
                    "status"
                ):
                    errors.append(f"{task_id}: task page projection differs from authoritative backlog")
                expected_dependencies = list(source_task.get("dependencies", []))
                expected_claim = {
                    "owner": source_task.get("owner") or (source_task.get("claim") or {}).get("agent"),
                    "branch": source_task.get("branch") or (source_task.get("claim") or {}).get("branch"),
                    "base_sha": source_task.get("base_sha") or (source_task.get("claim") or {}).get("base_sha"),
                }
                plan_section = extract_task_section(source_body, task_id)
                expected_plan_hash = text_sha256(plan_section) if plan_section else None
                if task_entry.get("dependencies") != expected_dependencies:
                    errors.append(f"{task_id}: dependency manifest differs from authoritative backlog order")
                if task_entry.get("claim") != expected_claim:
                    errors.append(f"{task_id}: claim manifest differs from authoritative backlog")
                if task_entry.get("plan_section_sha256") != expected_plan_hash:
                    errors.append(f"{task_id}: task-plan manifest hash differs from the authored slice plan")
                task_page = site / str(task_entry.get("page") or "")
                if not task_page.exists():
                    errors.append(f"{task_id}: missing task page {task_page}")
                    continue
                worksheet_path = repo / "artifacts" / "evidence" / f"{task_id}.task-start.md"
                expected_worksheet = (
                    {
                        "path": worksheet_path.relative_to(repo).as_posix(),
                        "sha256": sha256(worksheet_path),
                    }
                    if worksheet_path.is_file()
                    else None
                )
                if task_entry.get("worksheet") != expected_worksheet:
                    errors.append(f"{task_id}: optional worksheet projection differs from task-keyed source")
                task_text = task_page.read_text(encoding="utf-8")
                if f'data-task-page="{html.escape(task_id, quote=True)}"' not in task_text:
                    errors.append(f"{task_id}: task page is missing its task identity marker")
                dependency_inventory = "|".join(str(item) for item in expected_dependencies)
                if f'data-task-dependencies="{html.escape(dependency_inventory, quote=True)}"' not in task_text:
                    errors.append(f"{task_id}: rendered dependency inventory differs from authoritative backlog")
                rendered_dependencies = [
                    html.unescape(value) for value in re.findall(r'data-task-dependency="([^"]+)"', task_text)
                ]
                if rendered_dependencies != [str(item) for item in expected_dependencies]:
                    errors.append(f"{task_id}: rendered dependency order differs from authoritative backlog")
                for attribute, value in (
                    ("data-task-owner", expected_claim["owner"] or "unclaimed"),
                    ("data-task-branch", expected_claim["branch"] or "none"),
                    ("data-task-base-sha", expected_claim["base_sha"] or "none"),
                ):
                    if f'{attribute}="{html.escape(str(value), quote=True)}"' not in task_text:
                        errors.append(f"{task_id}: rendered claim projection differs at {attribute}")
                if (
                    not expected_plan_hash
                    or f'data-task-plan="{html.escape(task_id, quote=True)}"' not in task_text
                    or f'data-task-plan-sha256="{expected_plan_hash}"' not in task_text
                ):
                    errors.append(f"{task_id}: authored task-plan projection is missing or altered")
                worksheet_marker = f'data-task-worksheet="{html.escape(task_id, quote=True)}"'
                absent_marker = f'data-task-worksheet-absent="{html.escape(task_id, quote=True)}"'
                if expected_worksheet and worksheet_marker not in task_text:
                    errors.append(f"{task_id}: assigned worksheet is not rendered on the task page")
                if expected_worksheet is None and absent_marker not in task_text:
                    errors.append(f"{task_id}: task page does not truthfully report worksheet absence")
                errors.extend(
                    f"{task_id}: {error}"
                    for error in task_review_render_errors(task_text, task_review_projection(source_task))
                )

    if set(manifest_slices) != set(slice_plans):
        errors.append(f"Manifest slice set differs from plans: {len(manifest_slices)} vs {len(slice_plans)}")
    if set(manifest_tasks) != set(backlog_tasks):
        errors.append(
            f"Manifest task set differs from backlog: manifest={len(manifest_tasks)} backlog={len(backlog_tasks)}"
        )

    backlog_waves = {str(wave["id"]): wave for wave in backlog.get("waves", [])}
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
        expected_task_ids = [
            str(task["id"])
            for slice_ in backlog_slices.values()
            if slice_.get("wave") == wave_id
            for task in slice_.get("tasks", [])
        ]
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
        if [str(task_id) for task_id in entry.get("task_ids", [])] != expected_task_ids:
            errors.append(f"{wave_id}: wave task inventory differs from authoritative backlog order")
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
        expected_recoveries = sorted(
            request_id
            for request_id, hold in recovery_holds.items()
            if hold.get("target_wave") == wave_id and hold.get("status") == "ACTIVE"
        )
        if sorted(entry.get("interrupting_recovery_request_ids", [])) != expected_recoveries:
            errors.append(f"{wave_id}: interrupting recovery inventory differs from source authority")
    duplicate_assignments = sorted(slice_id for slice_id, count in Counter(assigned_slice_ids).items() if count != 1)
    if set(assigned_slice_ids) != set(backlog_slices) or duplicate_assignments:
        errors.append(f"Every backlog slice must appear in exactly one wave page; duplicates={duplicate_assignments}")

    html_pages = sorted(site.rglob("*.html"))
    expected_html = (
        3
        + len(ecr_packets)
        + len(recovery_holds)
        + len(backlog_waves)
        + len(cap_plans)
        + len(slice_plans)
        + len(backlog_tasks)
    )
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
            wave_manifest = manifest_waves.get(wave_id) or {}
            if parsed.wave_capability_ids != [str(value) for value in wave_manifest.get("capability_ids", [])]:
                errors.append(f"{rel}: collapsible capability cards differ from Wave inventory")
            if parsed.wave_slice_ids != [str(value) for value in wave_manifest.get("slice_ids", [])]:
                errors.append(f"{rel}: collapsible slice cards differ from Wave inventory")
            if parsed.wave_task_ids != [str(value) for value in wave_manifest.get("task_ids", [])]:
                errors.append(f"{rel}: collapsible task cards differ from Wave inventory")
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
            if (manifest_waves.get(wave_id) or {}).get("interrupting_recovery_request_ids"):
                for marker in (
                    "ordinary execution is interrupted",
                    "bootstrap-only",
                    "Exact ordinary resume condition",
                ):
                    if marker not in content:
                        errors.append(f"{rel}: interrupted Wave is missing governance recovery marker {marker}")
                if f"wave start {wave_id}" in text or f"wave approve {wave_id}" in text:
                    errors.append(f"{rel}: recovery-interrupted Wave advertises start or repeated approval")
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
                    "Materialized task review packets and history",
                    "Safe resume boundary",
                ):
                    if marker not in content:
                        errors.append(f"{rel}: missing ECR detail marker {marker}")
        elif page.parent.name == "recoveries":
            content = " ".join(parsed.text_parts)
            if page.name == "index.html":
                if "Governance recovery request register" not in content:
                    errors.append(f"{rel}: missing governance recovery register heading")
            else:
                request_id = page.stem
                if request_id not in recovery_holds:
                    errors.append(f"{rel}: recovery page has no matching backlog hold")
                for marker in ("Ordinary execution is denied", "Hash-bound source records", "Exact release conditions"):
                    if marker not in content:
                        errors.append(f"{rel}: missing governance recovery detail marker {marker}")
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
            page_id = page.stem
            content = " ".join(parsed.text_parts)
            if page_id in slice_plans:
                if parsed.page_type != "slice":
                    errors.append(f"{rel}: slice page has the wrong page type")
                if "Capability decision gate" not in content:
                    errors.append(f"{rel}: missing capability decision gate near top")
                if "Recommended implementation selections" not in content:
                    warnings.append(f"{rel}: slice decision summary heading not found")
                if "Open a task for its objective" not in content:
                    errors.append(f"{rel}: missing slice-to-task drill-down guidance")
            elif page_id in manifest_tasks:
                if parsed.page_type != "task":
                    errors.append(f"{rel}: task page has the wrong page type")
                for marker in ("Scope and acceptance", "Profiles and commands", "Assigned worksheet", "Review packets"):
                    if marker not in content:
                        errors.append(f"{rel}: missing task detail marker {marker}")
            else:
                errors.append(f"{rel}: capability child page has no matching slice or task")

    for required in [
        site / "assets/review.css",
        site / "assets/review.js",
        site / "enablers/index.html",
        site / "recoveries/index.html",
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
        "task_count": len(backlog_tasks),
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
        f"{len(slice_plans)} slices, {len(backlog_tasks)} tasks, {len(html_pages)} HTML pages"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
