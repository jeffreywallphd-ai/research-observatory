#!/usr/bin/env python3
"""Render deterministic human-readable views of the authoritative backlog."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import yaml
from taskctl import backlog_schema_errors, index_backlog

PLAN_VIEW = Path("docs/planning-implementation-plan.md")
STATUS_VIEW = Path("planning/status-summary.md")
GENERATED_WARNING = (
    "> **GENERATED FILE - DO NOT EDIT.** `planning/backlog.yaml` is authoritative. "
    "Run `python tools/backlog_views.py --repo .` to regenerate this file."
)


def inline(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return " ".join(str(value).split()).replace("|", "\\|")


def joined(values: list[Any] | None, *, code: bool = False) -> str:
    if not values:
        return "-"
    rendered = [inline(value) for value in values]
    if code:
        rendered = [f"`{value}`" for value in rendered]
    return ", ".join(rendered)


def bullets(lines: list[str], values: list[Any] | None) -> None:
    if not values:
        lines.append("- None")
        return
    lines.extend(f"- {inline(value)}" for value in values)


def capability_label(capability: dict[str, Any]) -> str:
    return f"{inline(capability.get('alias', capability['id']))} (`{capability['id']}`)"


def slice_label(slice_: dict[str, Any]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(slice_.get("title", "untitled")).lower()).strip("-")
    return f"SLICE-{slug} (`{slice_['id']}`)"


def source_digest(payload: bytes) -> str:
    payload = payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(payload).hexdigest()


def canonical_root(root: Path) -> Path:
    try:
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise SystemExit(f"Cannot resolve repository root {root}: {exc}") from exc
    if not resolved.is_dir():
        raise SystemExit(f"Repository root is not a directory: {resolved}")
    return resolved


def require_inside(root: Path, path: Path, label: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"{label} must resolve inside repository {root}: {path}") from exc
    return resolved


def output_destination(root: Path, relative: Path) -> Path:
    lexical = root / relative
    try:
        parent = lexical.parent.resolve(strict=False)
        parent.relative_to(root)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Generated view parent escapes repository: {relative.parent}") from exc
    destination = parent / lexical.name
    if destination.exists() or destination.is_symlink():
        try:
            resolved_destination = destination.resolve(strict=True)
            resolved_destination.relative_to(root)
        except (OSError, ValueError) as exc:
            raise SystemExit(f"Generated view path escapes repository: {relative}") from exc
        if resolved_destination != destination:
            raise SystemExit(f"Generated view path must not be a symbolic link or redirect: {relative}")
    return destination


def parse_backlog_snapshot(payload: bytes, schema_path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(payload.decode("utf-8"))
    except (UnicodeError, yaml.YAMLError) as exc:
        raise SystemExit(f"Cannot parse backlog snapshot: {exc}") from exc
    schema_errors = backlog_schema_errors(data, schema_path=schema_path)
    if schema_errors:
        raise SystemExit("Backlog schema validation failed:\n- " + "\n- ".join(schema_errors))
    indexed, *_ = index_backlog(data)
    return indexed


def hierarchy(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    capabilities = data.get("capabilities", [])
    slices = [slice_ for capability in capabilities for slice_ in capability.get("slices", [])]
    tasks = [task for slice_ in slices for task in slice_.get("tasks", [])]
    return capabilities, slices, tasks


def enabler_tasks(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        task
        for amendment in data.get("wave_amendments", [])
        if isinstance(amendment, dict)
        for task in amendment.get("tasks", [])
        if isinstance(task, dict)
    ]


def wave_authority_rows(data: dict[str, Any]) -> list[tuple[str, str, str, str, str]]:
    rows: list[tuple[str, str, str, str, str]] = []
    for base in data.get("wave_approval_bases", []):
        rows.append(
            (
                inline(base.get("wave_id")),
                "BASE",
                inline(base.get("packet_commit")),
                inline(base.get("record_commit")),
                "APPROVED",
            )
        )
    for amendment in data.get("wave_amendments", []):
        reference = amendment.get("approval_reference") or {}
        rows.append(
            (
                inline(amendment.get("target_wave")),
                inline(amendment.get("id")),
                inline(amendment.get("change_request_id")),
                inline(reference.get("path")),
                inline((amendment.get("lifecycle") or {}).get("status")),
            )
        )
    return rows


def task_open_finding_ids(task: dict[str, Any]) -> list[str]:
    control = task.get("review_control")
    if not isinstance(control, dict):
        return []
    open_ids: set[str] = set()
    for attempt in control.get("attempts") or []:
        for closure in attempt.get("closures") or []:
            open_ids.discard(str(closure.get("finding_id")))
        for finding in attempt.get("findings") or []:
            open_ids.add(str(finding.get("id")))
    return sorted(open_ids)


def _submission_packet_markdown(packet: dict[str, Any], *, label: str) -> list[str]:
    evidence = packet.get("evidence_reference") or {}
    return [
        f"**{label}:** `{inline(packet.get('id'))}` / packet SHA-256 `{inline(packet.get('packet_sha256'))}`",
        "",
        f"- Candidate / base / branch: `{inline(packet.get('candidate_commit'))}` / "
        f"`{inline(packet.get('base_commit'))}` / `{inline(packet.get('branch'))}`",
        f"- Submitted by / at: {inline(packet.get('submitted_by'))} / `{inline(packet.get('submitted_at'))}`",
        f"- Evidence: `{inline(evidence.get('path'))}` / `{inline(evidence.get('sha256'))}` / "
        f"`{inline(evidence.get('commit'))}`",
        f"- Acceptance-criteria SHA-256: `{inline(packet.get('acceptance_criteria_sha256'))}`",
        f"- Verification-selection SHA-256: `{inline(packet.get('selection_sha256'))}`",
        f"- Changed paths: {joined(packet.get('changed_paths'), code=True)}",
        f"- Selected checks: {joined(packet.get('selected_checks'), code=True)}",
        f"- Deferred checks: {joined(packet.get('deferred_checks'), code=True)}",
        f"- Selection rationale: {inline(packet.get('selection_rationale'))}",
        f"- Prior round / replayed open findings: `{inline(packet.get('prior_attempt_id'))}` / "
        f"{joined(packet.get('open_finding_ids'), code=True)}",
        f"- Root-cause escalation: {inline(packet.get('root_cause_analysis'))}",
        "",
    ]


def task_review_markdown(task: dict[str, Any], *, heading_level: int) -> list[str]:
    prefix = "#" * heading_level
    task_id = inline(task.get("id"))
    review = task.get("review") or {}
    control = task.get("review_control")
    lines = [f"{prefix} Review history — {task_id}", ""]
    if not isinstance(control, dict):
        lines.extend(
            [
                "**Review mode:** `legacy latest-review-only projection` — no append-only rounds are recorded; "
                "this view does not fabricate historical attempts.",
                "",
                f"**Current latest-review projection:** `{inline(review.get('result'))}` by "
                f"{inline(review.get('reviewer'))} at `{inline(review.get('reviewed_at'))}`",
                "",
                f"**Latest notes:** {inline(review.get('notes'))}",
                "",
            ]
        )
        return lines

    attempts = control.get("attempts") or []
    lines.extend(
        [
            f"**Review mode:** `append-only v{inline(control.get('version'))}` / {len(attempts)} completed round(s)",
            "",
        ]
    )
    for attempt in attempts:
        packet = attempt.get("submission") or {}
        attempt_review = attempt.get("review") or {}
        ledger = attempt.get("ledger") or {}
        attempt_id = inline(packet.get("id"))
        lines.extend([f"{prefix}# Round {attempt_id}", ""])
        lines.extend(_submission_packet_markdown(packet, label="Immutable submission packet"))
        lines.extend(
            [
                f"**Disposition / reviewer / time:** `{inline(attempt_review.get('result'))}` / "
                f"{inline(attempt_review.get('reviewer'))} / `{inline(attempt_review.get('reviewed_at'))}`",
                "",
                f"**Immutable review ledger:** `{inline(ledger.get('path'))}` / `{inline(ledger.get('sha256'))}`",
                "",
                f"**Review notes:** {inline(attempt_review.get('notes'))}",
                "",
                "**Findings opened:**",
                "",
            ]
        )
        findings = attempt.get("findings") or []
        if findings:
            lines.extend(
                f"- `{inline(finding.get('id'))}` `{inline(finding.get('severity'))}` "
                f"blocking=`{inline(finding.get('blocking'))}` criterion=`{inline(finding.get('criterion_index'))}` — "
                f"{inline(finding.get('title'))}; reproduce: {inline(finding.get('reproduction'))}; "
                f"remediate: {inline(finding.get('required_remediation'))}"
                for finding in findings
            )
        else:
            lines.append("- None")
        lines.extend(["", "**Prior finding closures:**", ""])
        closures = attempt.get("closures") or []
        if closures:
            lines.extend(
                f"- `{inline(closure.get('finding_id'))}` `{inline(closure.get('disposition'))}` — "
                f"{inline(closure.get('evidence'))}"
                for closure in closures
            )
        else:
            lines.append("- None")
        lines.append("")
    current = control.get("current_submission")
    if isinstance(current, dict):
        lines.extend(_submission_packet_markdown(current, label="Current immutable submission awaiting review"))
    else:
        lines.extend(["**Current immutable submission awaiting review:** None", ""])
    lines.extend(
        [
            f"**Current latest-review projection:** `{inline(review.get('result'))}` by "
            f"{inline(review.get('reviewer'))} at `{inline(review.get('reviewed_at'))}`",
            "",
            f"**Latest notes:** {inline(review.get('notes'))}",
            "",
            f"**Currently open findings:** {joined(task_open_finding_ids(task), code=True)}",
            "",
        ]
    )
    return lines


def status_table(lines: list[str], title: str, statuses: Counter[str], order: list[str] | None = None) -> None:
    lines.extend([f"### {title}", "", "| Status | Count |", "|---|---:|"])
    keys = [key for key in (order or []) if key in statuses]
    keys.extend(sorted(set(statuses) - set(keys)))
    lines.extend(f"| `{status}` | {statuses[status]} |" for status in keys)
    lines.append("")


def render_summary(data: dict[str, Any], digest: str) -> str:
    capabilities, slices, tasks = hierarchy(data)
    amendments = data.get("wave_amendments", [])
    amendment_tasks = enabler_tasks(data)
    waves = data.get("waves", [])
    gates = data.get("release_gates", [])
    task_order = list(data.get("status_definitions", {}))
    lines = [
        "---",
        "document_type: generated-backlog-status-summary",
        "source: planning/backlog.yaml",
        f"source_sha256: {digest}",
        "generator: tools/backlog_views.py",
        "manual_edit: prohibited",
        "---",
        "",
        "# Backlog status summary",
        "",
        GENERATED_WARNING,
        "",
        "## Ledger totals",
        "",
        "| Item | Count |",
        "|---|---:|",
        f"| Capabilities | {len(capabilities)} |",
        f"| Slices | {len(slices)} |",
        f"| Tasks | {len(tasks)} |",
        f"| Enabler tasks | {len(amendment_tasks)} |",
        f"| Waves | {len(waves)} |",
        f"| Wave approval bases | {len(data.get('wave_approval_bases', []))} |",
        f"| Wave amendments | {len(amendments)} |",
        f"| Release gates | {len(gates)} |",
        "",
        "## Status distributions",
        "",
    ]
    status_table(
        lines,
        "Capability completion",
        Counter(inline(capability.get("completion", {}).get("status")) for capability in capabilities),
    )
    status_table(
        lines,
        "Wave campaign state",
        Counter(inline((wave.get("campaign") or {}).get("status", "NONE")) for wave in waves),
    )
    status_table(
        lines,
        "Slice completion",
        Counter(inline(slice_.get("completion", {}).get("status")) for slice_ in slices),
    )
    status_table(lines, "Task state", Counter(inline(task.get("status")) for task in tasks), task_order)
    status_table(
        lines,
        "Wave amendment lifecycle",
        Counter(inline((amendment.get("lifecycle") or {}).get("status")) for amendment in amendments),
    )
    status_table(
        lines,
        "Enabler task state",
        Counter(inline(task.get("status")) for task in amendment_tasks),
        task_order,
    )

    lines.extend(
        [
            "## Wave authority and append-only amendments",
            "",
            "Proposal approval, materialization lifecycle, and campaign state remain distinct. "
            "A Wave approval is immutable; later authority is an ordered amendment record.",
            "",
            "| Wave | Authority | Packet / ECR | Approval record | Lifecycle | Bootstrap | Campaign | Enabler tasks |",
            "|---|---|---|---|---|---|---|---:|",
        ]
    )
    amendments_by_id = {str(item.get("id")): item for item in amendments}
    for wave_id, authority_id, packet_or_ecr, record, lifecycle in wave_authority_rows(data):
        amendment = amendments_by_id.get(authority_id)
        if amendment is None:
            lines.append(
                f"| `{wave_id}` | `{authority_id}` | `{packet_or_ecr}` | `{record}` | `{lifecycle}` | - | - | 0 |"
            )
            continue
        bootstrap = amendment.get("bootstrap") or {}
        campaign = amendment.get("campaign") or {}
        lines.append(
            f"| `{wave_id}` | `{authority_id}` | `{packet_or_ecr}` | `{record}` | `{lifecycle}` | "
            f"`{inline(bootstrap.get('status', 'NONE'))}` | `{inline(campaign.get('status', 'NONE'))}` | "
            f"{len(amendment.get('tasks', []))} |"
        )
    if not wave_authority_rows(data):
        lines.append("| - | - | - | - | - | - | - | 0 |")

    review_tasks = [
        task
        for task in tasks + amendment_tasks
        if isinstance(task.get("review_control"), dict)
        or any((task.get("review") or {}).get(key) is not None for key in ("result", "reviewer", "reviewed_at"))
    ]
    lines.extend(
        [
            "",
            "## Task review history projections",
            "",
            "Append-only rounds remain distinct from the current latest-review projection. Legacy records are labeled "
            "latest-review-only and receive no synthesized rounds.",
            "",
            "| Task | Mode | Completed rounds | Current submission | Latest projection | Open findings |",
            "|---|---|---:|---|---|---|",
        ]
    )
    for task in review_tasks:
        control = task.get("review_control")
        review = task.get("review") or {}
        if isinstance(control, dict):
            mode = f"append-only v{inline(control.get('version'))}"
            round_count = len(control.get("attempts") or [])
            current = (control.get("current_submission") or {}).get("id") or "-"
        else:
            mode = "legacy latest-review-only"
            round_count = 0
            current = "-"
        latest = f"{inline(review.get('result'))} / {inline(review.get('reviewer'))}"
        lines.append(
            f"| `{inline(task.get('id'))}` | `{mode}` | {round_count} | `{inline(current)}` | "
            f"{latest} | {joined(task_open_finding_ids(task), code=True)} |"
        )
    if not review_tasks:
        lines.append("| - | - | 0 | - | - | - |")

    lines.extend(
        [
            "## Wave progress",
            "",
            "| Wave | Pre-Wave approval | Campaign | Qualification | Approved slices | Done tasks | Exit gate |",
            "|---|---|---|---|---:|---:|---|",
        ]
    )
    for wave in waves:
        wave_id = wave.get("id")
        wave_slices = [slice_ for slice_ in slices if slice_.get("wave") == wave_id]
        wave_tasks = [task for slice_ in wave_slices for task in slice_.get("tasks", [])]
        gate: dict[str, Any] = next((item for item in gates if item.get("after_wave") == wave_id), {})
        approved_count = sum(item.get("completion", {}).get("status") == "APPROVED" for item in wave_slices)
        lines.append(
            f"| `{inline(wave_id)}` - {inline(wave.get('title'))} | "
            f"`{inline((wave.get('approval') or {}).get('status', 'PENDING'))}` | "
            f"`{inline((wave.get('campaign') or {}).get('status', 'NONE'))}` | "
            f"`{inline((wave.get('completion') or {}).get('status', 'PENDING'))}` | "
            f"{approved_count}/{len(wave_slices)} | "
            f"{sum(item.get('status') == 'DONE' for item in wave_tasks)}/{len(wave_tasks)} | "
            f"`{inline(gate.get('id'))}` / `{inline(gate.get('status'))}` |"
        )

    lines.extend(
        [
            "",
            "## Capability progress",
            "",
            "| Capability contribution | Legacy campaign | Completion | Approved slices | Done tasks | Active task |",
            "|---|---|---|---:|---:|---|",
        ]
    )
    for capability in capabilities:
        cap_slices = capability.get("slices", [])
        cap_tasks = [task for slice_ in cap_slices for task in slice_.get("tasks", [])]
        approved_slices = sum(slice_.get("completion", {}).get("status") == "APPROVED" for slice_ in cap_slices)
        done_tasks = sum(task.get("status") == "DONE" for task in cap_tasks)
        active = [task["id"] for task in cap_tasks if task.get("status") in {"IN_PROGRESS", "REVIEW", "BLOCKED"}]
        lines.append(
            f"| {capability_label(capability)} — {inline(capability.get('title'))} | "
            f"`{inline((capability.get('campaign') or {}).get('status', 'NONE'))}` | "
            f"`{inline(capability.get('completion', {}).get('status'))}` | "
            f"{approved_slices}/{len(cap_slices)} | {done_tasks}/{len(cap_tasks)} | {joined(active, code=True)} |"
        )

    lines.extend(["", "## Release gates", "", "| Gate | After wave | Unlocks | Status |", "|---|---|---|---|"])
    for gate in gates:
        lines.append(
            f"| `{gate['id']}` — {inline(gate.get('after_wave'))} exit / "
            f"{joined(gate.get('unlocks_waves'))} activation — {inline(gate.get('name'))} | "
            f"`{inline(gate.get('after_wave'))}` | "
            f"{joined(gate.get('unlocks_waves'), code=True)} | `{inline(gate.get('status'))}` |"
        )

    active_tasks = [
        task for task in tasks + amendment_tasks if task.get("status") in {"IN_PROGRESS", "REVIEW", "BLOCKED"}
    ]
    lines.extend(["", "## Active work", ""])
    if not active_tasks:
        lines.append("No task is currently active.")
    else:
        lines.extend(["| Task | Status | Owner | Branch |", "|---|---|---|---|"])
        for task in active_tasks:
            lines.append(
                f"| `{task['id']}` {inline(task.get('title'))} | `{inline(task.get('status'))}` | "
                f"{inline(task.get('owner'))} | `{inline(task.get('branch'))}` |"
            )
    lines.append("")
    return "\n".join(lines)


def render_plan(data: dict[str, Any], digest: str) -> str:
    capabilities, slices, tasks = hierarchy(data)
    amendments = data.get("wave_amendments", [])
    amendment_tasks = enabler_tasks(data)
    waves = data.get("waves", [])
    plan = data.get("plan", {})
    lines = [
        "---",
        "document_type: generated-backlog-plan",
        f"plan_id: {inline(plan.get('id'))}",
        f"plan_version: {inline(plan.get('version'))}",
        "source: planning/backlog.yaml",
        f"source_sha256: {digest}",
        "generator: tools/backlog_views.py",
        "manual_edit: prohibited",
        "---",
        "",
        f"# {inline(plan.get('title', 'Implementation plan'))}",
        "",
        GENERATED_WARNING,
        "",
        "## Authority and scope",
        "",
        inline(plan.get("authority")),
        "",
        f"**Delivery priority:** {inline(plan.get('primary_delivery_priority'))}",
        "",
        f"**Permanent ID policy:** {inline(plan.get('task_id_policy'))}",
        "",
        "## Ledger snapshot",
        "",
        "| Item | Count |",
        "|---|---:|",
        f"| Capabilities | {len(capabilities)} |",
        f"| Slices | {len(slices)} |",
        f"| Tasks | {len(tasks)} |",
        f"| Enabler tasks | {len(amendment_tasks)} |",
        f"| Waves | {len(data.get('waves', []))} |",
        f"| Wave approval bases | {len(data.get('wave_approval_bases', []))} |",
        f"| Wave amendments | {len(amendments)} |",
        f"| Release gates | {len(data.get('release_gates', []))} |",
        "",
        "See `planning/status-summary.md` for the generated status distributions and capability progress table.",
        "",
        "## Ordered Wave authority",
        "",
        "| Wave | Authority | Packet / ECR | Approval record | Lifecycle |",
        "|---|---|---|---|---|",
    ]
    authority_rows = wave_authority_rows(data)
    if authority_rows:
        lines.extend(
            f"| `{wave_id}` | `{authority_id}` | `{packet_or_ecr}` | `{record}` | `{lifecycle}` |"
            for wave_id, authority_id, packet_or_ecr, record, lifecycle in authority_rows
        )
    else:
        lines.append("| - | - | - | - | - |")
    lines.extend(
        [
            "",
            "## Waves",
            "",
            "| Wave | Track | Goal | Activation |",
            "|---|---|---|---|",
        ]
    )
    for wave in data.get("waves", []):
        activation = f"`{wave['activation_gate']}`" if wave.get("activation_gate") else "Initial"
        lines.append(
            f"| `{wave['id']}` {inline(wave.get('title'))} | {inline(wave.get('track'))} | "
            f"{inline(wave.get('goal'))} | {activation} |"
        )

    lines.extend(["", "## Release gates", ""])
    for gate in data.get("release_gates", []):
        lines.extend(
            [
                f"### {gate['id']} - {inline(gate.get('name'))}",
                "",
                f"**After / unlocks / status:** `{inline(gate.get('after_wave'))}` / "
                f"{joined(gate.get('unlocks_waves'), code=True)} / `{inline(gate.get('status'))}`",
                "",
                "**Criteria:**",
                "",
            ]
        )
        bullets(lines, gate.get("criteria"))
        lines.append("")

    lines.extend(["## Architecture constraints", ""])
    bullets(lines, data.get("architecture_constraints"))
    lines.extend(["", "## Selection policy", ""])
    bullets(lines, data.get("selection_policy"))
    lines.extend(["", "## Definition of ready", ""])
    bullets(lines, data.get("definition_of_ready"))
    lines.extend(["", "## Definition of done", ""])
    bullets(lines, data.get("definition_of_done"))

    lines.extend(["", "# Wave campaign plan", ""])
    for wave in waves:
        wave_id = wave.get("id")
        wave_slices = [slice_ for slice_ in slices if slice_.get("wave") == wave_id]
        wave_capabilities = sorted({str(slice_["id"]).split(".")[0] for slice_ in wave_slices})
        lines.extend(
            [
                f"## {inline(wave_id)} - {inline(wave.get('title'))}",
                "",
                f"**Pre-Wave approval / campaign / qualification:** "
                f"`{inline((wave.get('approval') or {}).get('status', 'PENDING'))}` / "
                f"`{inline((wave.get('campaign') or {}).get('status', 'NONE'))}` / "
                f"`{inline((wave.get('completion') or {}).get('status', 'PENDING'))}`",
                "",
                f"**Capability contributions:** {joined(wave_capabilities, code=True)}",
                "",
                f"**Ordered slices:** {joined([slice_['id'] for slice_ in wave_slices], code=True)}",
                "",
                f"**Goal:** {inline(wave.get('goal'))}",
                "",
            ]
        )

    lines.extend(["", "# Enabler change requests and Wave amendments", ""])
    if not amendments:
        lines.extend(
            [
                "No Wave amendment has been materialized in the authoritative ledger.",
                "",
                "Hash-bound proposals and approvals remain visible in the generated planning review site's "
                "enabler register.",
                "",
            ]
        )
    for amendment in amendments:
        lifecycle = amendment.get("lifecycle") or {}
        bootstrap = amendment.get("bootstrap") or {}
        campaign = amendment.get("campaign") or {}
        completion = amendment.get("completion") or {}
        reference = amendment.get("approval_reference") or {}
        lines.extend(
            [
                f"## {inline(amendment.get('id'))} - {inline(amendment.get('change_request_id'))}",
                "",
                f"**Target Wave / class:** `{inline(amendment.get('target_wave'))}` / "
                f"`{inline(amendment.get('kind'))}`",
                "",
                f"**Approval record:** `{inline(reference.get('path'))}` (`{inline(reference.get('sha256'))}`)",
                "",
                f"**Lifecycle / bootstrap / campaign / completion:** `{inline(lifecycle.get('status'))}` / "
                f"`{inline(bootstrap.get('status', 'NONE'))}` / `{inline(campaign.get('status', 'NONE'))}` / "
                f"`{inline(completion.get('status'))}`",
                "",
                "**Append-only lifecycle history:**",
                "",
            ]
        )
        if lifecycle.get("history"):
            lines.extend(
                f"- `{inline(event.get('id'))}` `{inline(event.get('status'))}` at "
                f"`{inline(event.get('at'))}` by {inline(event.get('actor'))}: {inline(event.get('rationale'))}"
                for event in lifecycle["history"]
            )
        else:
            lines.append("- None")
        lines.extend(["", "**Bounded tasks:**", ""])
        for task in amendment.get("tasks", []):
            checked = "x" if task.get("status") == "DONE" else " "
            review = task.get("review") or {}
            lines.extend(
                [
                    f"### - [{checked}] {task['id']} - {inline(task.get('title'))}",
                    "",
                    f"**Status / owner / review:** `{inline(task.get('status'))}` / {inline(task.get('owner'))} / "
                    f"{inline(review.get('reviewer'))} (`{inline(review.get('result'))}`)",
                    "",
                    f"**Dependencies:** {joined(task.get('dependencies'), code=True)}",
                    "",
                    f"**Objective:** {inline(task.get('objective'))}",
                    "",
                    "**Acceptance criteria:**",
                    "",
                ]
            )
            bullets(lines, task.get("acceptance_criteria"))
            lines.extend(["", "**Verification:**", ""])
            bullets(lines, task.get("verification_commands"))
            if task.get("evidence"):
                lines.extend(["", "**Evidence:**", ""])
                lines.extend(
                    f"- `{reference.get('path')}` at `{inline(reference.get('commit'))}`"
                    for reference in task["evidence"]
                )
            lines.append("")
            lines.extend(task_review_markdown(task, heading_level=4))

    lines.extend(["", "# Capability contributions, slices, and tasks", ""])
    for capability in capabilities:
        campaign = capability.get("campaign") or {}
        completion = capability.get("completion", {})
        lines.extend(
            [
                f"## {capability_label(capability)} - {inline(capability.get('title'))}",
                "",
                f"**Legacy campaign record / contribution completion:** `{inline(campaign.get('status', 'NONE'))}` / "
                f"`{inline(completion.get('status'))}`",
                "",
                f"**Objective:** {inline(capability.get('objective'))}",
                "",
                "**Exit criteria:**",
                "",
            ]
        )
        bullets(lines, capability.get("exit_criteria"))
        lines.append("")

        for slice_ in capability.get("slices", []):
            slice_completion = slice_.get("completion", {})
            lines.extend(
                [
                    f"### {slice_label(slice_)} - {inline(slice_.get('title'))}",
                    "",
                    f"**Outcome:** {inline(slice_.get('outcome'))}",
                    "",
                    f"**Wave / priority / status / review:** `{inline(slice_.get('wave'))}` / "
                    f"`{inline(slice_.get('priority'))}` / `{inline(slice_.get('status'))}` / "
                    f"`{inline(slice_completion.get('status'))}`",
                    "",
                    f"**Profiles / platforms:** {joined(slice_.get('deployment_profiles'), code=True)} / "
                    f"{joined(slice_.get('platform_targets'), code=True)}",
                    "",
                    f"**Dependencies:** {joined(slice_.get('depends_on'), code=True)}",
                    "",
                ]
            )
            for task in slice_.get("tasks", []):
                checked = "x" if task.get("status") == "DONE" else " "
                review = task.get("review", {})
                lines.extend(
                    [
                        f"#### - [{checked}] {task['id']} - {inline(task.get('title'))}",
                        "",
                        f"**Status / priority / estimate / risk:** `{inline(task.get('status'))}` / "
                        f"`{inline(task.get('priority'))}` / `{inline(task.get('estimate'))}` / "
                        f"`{inline(task.get('risk'))}`",
                        "",
                        f"**Profiles / platforms:** {joined(task.get('deployment_profiles'), code=True)} / "
                        f"{joined(task.get('platform_targets'), code=True)}",
                        "",
                        f"**Dependencies:** {joined(task.get('dependencies'), code=True)}",
                        "",
                        f"**Owner / review:** {inline(task.get('owner'))} / "
                        f"{inline(review.get('reviewer'))} (`{inline(review.get('result'))}`)",
                        "",
                        f"**Objective:** {inline(task.get('objective'))}",
                        "",
                        "**Deliverables:**",
                        "",
                    ]
                )
                bullets(lines, task.get("deliverables"))
                lines.extend(["", "**Acceptance criteria:**", ""])
                bullets(lines, task.get("acceptance_criteria"))
                lines.extend(["", "**Verification:**", ""])
                bullets(lines, task.get("verification_commands"))
                if task.get("evidence"):
                    lines.extend(["", "**Evidence:**", ""])
                    lines.extend(
                        f"- `{reference.get('path')}` at `{inline(reference.get('commit'))}`"
                        for reference in task["evidence"]
                    )
                lines.append("")
                lines.extend(task_review_markdown(task, heading_level=5))

    lines.extend(
        [
            "# Generation contract",
            "",
            "Do not hand-edit any section of this file. Change `planning/backlog.yaml`, validate it, and run:",
            "",
            "```bash",
            "python tools/backlog_views.py --repo .",
            "python tools/backlog_views.py --repo . --check",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def expected_outputs(root: Path) -> dict[Path, str]:
    root = canonical_root(root)
    backlog = require_inside(root, root / "planning/backlog.yaml", "Backlog source")
    schema = require_inside(root, root / "planning/backlog.schema.json", "Backlog schema")
    try:
        payload = backlog.read_bytes()
    except OSError as exc:
        raise SystemExit(f"Cannot read backlog source {backlog}: {exc}") from exc
    data = parse_backlog_snapshot(payload, schema)
    digest = source_digest(payload)
    return {
        output_destination(root, PLAN_VIEW): render_plan(data, digest),
        output_destination(root, STATUS_VIEW): render_summary(data, digest),
    }


def synchronize(root: Path, *, check: bool) -> tuple[list[Path], list[Path]]:
    root = canonical_root(root)
    stale: list[Path] = []
    updated: list[Path] = []
    for destination, expected in expected_outputs(root).items():
        expected_payload = expected.encode("utf-8")
        relative = destination.relative_to(root)
        try:
            current = destination.read_bytes()
        except FileNotFoundError:
            current = b""
        except OSError as exc:
            raise SystemExit(f"Cannot read generated backlog view {relative}: {exc}") from exc
        if current == expected_payload:
            continue
        stale.append(relative)
        if check:
            continue
        temp_name: str | None = None
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            safe_destination = output_destination(root, relative)
            fd, temp_name = tempfile.mkstemp(
                prefix=f"{safe_destination.name}.", suffix=".tmp", dir=safe_destination.parent
            )
            with os.fdopen(fd, "wb") as handle:
                handle.write(expected_payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, safe_destination)
        except OSError as exc:
            try:
                if temp_name is not None and os.path.exists(temp_name):
                    os.unlink(temp_name)
            except OSError as cleanup_exc:
                raise SystemExit(
                    f"Cannot update generated backlog view {relative}: {exc}; "
                    f"temporary-file cleanup also failed: {cleanup_exc}"
                ) from exc
            raise SystemExit(f"Cannot update generated backlog view {relative}: {exc}") from exc
        updated.append(relative)
    return stale, updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="repository root")
    parser.add_argument("--check", action="store_true", help="fail if a generated view is missing or stale")
    args = parser.parse_args()
    root = Path(args.repo).resolve()
    stale, updated = synchronize(root, check=args.check)
    if args.check and stale:
        for path in stale:
            print(f"STALE generated backlog view: {path}")
        return 1
    if updated:
        for path in updated:
            print(f"Updated generated backlog view: {path}")
    else:
        print("Generated backlog views: PASS - no changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
