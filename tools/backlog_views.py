#!/usr/bin/env python3
"""Render deterministic human-readable views of the authoritative backlog."""

from __future__ import annotations

import argparse
import hashlib
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from taskctl import load

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


def source_digest(path: Path) -> str:
    payload = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(payload).hexdigest()


def hierarchy(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    capabilities = data.get("capabilities", [])
    slices = [slice_ for capability in capabilities for slice_ in capability.get("slices", [])]
    tasks = [task for slice_ in slices for task in slice_.get("tasks", [])]
    return capabilities, slices, tasks


def status_table(lines: list[str], title: str, statuses: Counter[str], order: list[str] | None = None) -> None:
    lines.extend([f"### {title}", "", "| Status | Count |", "|---|---:|"])
    keys = [key for key in (order or []) if key in statuses]
    keys.extend(sorted(set(statuses) - set(keys)))
    lines.extend(f"| `{status}` | {statuses[status]} |" for status in keys)
    lines.append("")


def render_summary(data: dict[str, Any], digest: str) -> str:
    capabilities, slices, tasks = hierarchy(data)
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
        "Campaign state",
        Counter(inline((capability.get("campaign") or {}).get("status", "NONE")) for capability in capabilities),
    )
    status_table(
        lines,
        "Slice completion",
        Counter(inline(slice_.get("completion", {}).get("status")) for slice_ in slices),
    )
    status_table(lines, "Task state", Counter(inline(task.get("status")) for task in tasks), task_order)

    lines.extend(
        [
            "## Capability progress",
            "",
            "| Capability | Campaign | Completion | Approved slices | Done tasks | Active task |",
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
            f"| `{capability['id']}` {inline(capability.get('title'))} | "
            f"`{inline((capability.get('campaign') or {}).get('status', 'NONE'))}` | "
            f"`{inline(capability.get('completion', {}).get('status'))}` | "
            f"{approved_slices}/{len(cap_slices)} | {done_tasks}/{len(cap_tasks)} | {joined(active, code=True)} |"
        )

    lines.extend(["", "## Release gates", "", "| Gate | After wave | Unlocks | Status |", "|---|---|---|---|"])
    for gate in gates:
        lines.append(
            f"| `{gate['id']}` {inline(gate.get('name'))} | `{inline(gate.get('after_wave'))}` | "
            f"{joined(gate.get('unlocks_waves'), code=True)} | `{inline(gate.get('status'))}` |"
        )

    active_tasks = [task for task in tasks if task.get("status") in {"IN_PROGRESS", "REVIEW", "BLOCKED"}]
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
        f"| Waves | {len(data.get('waves', []))} |",
        f"| Release gates | {len(data.get('release_gates', []))} |",
        "",
        "See `planning/status-summary.md` for the generated status distributions and capability progress table.",
        "",
        "## Waves",
        "",
        "| Wave | Track | Goal | Activation |",
        "|---|---|---|---|",
    ]
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

    lines.extend(["", "# Capability, slice, and task plan", ""])
    for capability in capabilities:
        campaign = capability.get("campaign") or {}
        completion = capability.get("completion", {})
        lines.extend(
            [
                f"## {capability['id']} - {inline(capability.get('title'))}",
                "",
                f"**Campaign / completion:** `{inline(campaign.get('status', 'NONE'))}` / "
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
                    f"### {slice_['id']} - {inline(slice_.get('title'))}",
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
    backlog = root / "planning/backlog.yaml"
    data, *_ = load(str(backlog))
    digest = source_digest(backlog)
    return {
        root / PLAN_VIEW: render_plan(data, digest),
        root / STATUS_VIEW: render_summary(data, digest),
    }


def synchronize(root: Path, *, check: bool) -> tuple[list[Path], list[Path]]:
    stale: list[Path] = []
    updated: list[Path] = []
    for destination, expected in expected_outputs(root).items():
        try:
            current = destination.read_text(encoding="utf-8")
        except FileNotFoundError:
            current = ""
        if current == expected:
            continue
        relative = destination.relative_to(root)
        stale.append(relative)
        if check:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f"{destination.name}.", suffix=".tmp", dir=destination.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(expected)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, destination)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
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
