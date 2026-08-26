#!/usr/bin/env python3
"""Read-only shadow projection for the repository's next legal action.

The first governance-automation simplification increment is deliberately
advisory.  It reuses the current backlog model, emits one typed decision, and
compares that decision's category with legacy ``taskctl next``.  It has no
mutation subcommands and grants no execution authority.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

import taskctl

SCHEMA_VERSION = "1.0"
DOCUMENT_TYPE = "governance-next-action-shadow"
DEFAULT_PROFILE = "LOC"
DEFAULT_PLATFORM = "windows-x64"


def repository_root(value: str) -> Path:
    root = Path(value).resolve()
    if not (root / ".git").exists() or not (root / "planning" / "backlog.yaml").is_file():
        raise SystemExit(f"Not a Research Observatory repository: {root}")
    return root


def fresh_index(
    data: dict[str, Any],
) -> tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    return taskctl.index_backlog(copy.deepcopy(taskctl.serializable_backlog(data)))


def decision(
    *,
    category: str,
    action: str,
    target: str | None,
    summary: str,
    command: str | None,
    risk_tier: int,
    executable_now: bool,
    approval_required: bool,
) -> dict[str, Any]:
    return {
        "category": category,
        "action": action,
        "target": target,
        "summary": summary,
        "command": command,
        "riskTier": risk_tier,
        "executableNow": executable_now,
        "approvalRequired": approval_required,
        "effect": "read-only" if risk_tier == 0 else "mutation-template",
    }


def recovery_decision(program: dict[str, Any]) -> dict[str, Any]:
    hold = program.get("recovery_hold") or {}
    request_id = str(hold.get("recovery_request_id") or "")
    hold_id = str(hold.get("id") or request_id or "unknown-recovery-hold")
    bootstrap = hold.get("bootstrap") or {}
    summary = (
        f"Inspect active recovery hold {hold_id}; ordinary Wave, task, amendment, and gate mutations remain denied. "
        f"Bootstrap {bootstrap.get('id') or 'unknown'} is {bootstrap.get('status') or 'UNKNOWN'}."
    )
    return decision(
        category="recovery-hold",
        action="inspect-recovery",
        target=hold_id,
        summary=summary,
        command=f"python tools/recoveryctl.py --repo . status {request_id}" if request_id else None,
        risk_tier=0,
        executable_now=bool(request_id),
        approval_required=False,
    )


def amendment_decision(data: dict[str, Any], program: dict[str, Any]) -> dict[str, Any]:
    active = taskctl.active_amendment_campaigns(data)
    amendment = active[0] if active else program.get("amendment") or {}
    amendment_id = str(amendment.get("id") or "unknown-amendment")
    ready = sorted(
        (item for item in amendment.get("tasks", []) if item.get("status") == "READY"),
        key=taskctl.task_sort_key,
    )
    if ready:
        task_id = str(ready[0]["id"])
        return decision(
            category="task",
            action="claim-amendment-task",
            target=task_id,
            summary=f"Claim the next dependency-eligible task in active amendment {amendment_id}.",
            command=(
                f"python tools/taskctl.py --file planning/backlog.yaml claim {task_id} --agent <agent> "
                "--branch <codex-branch> --base-sha <HEAD> --worktree <absolute-repository-path> "
                f"--profile {DEFAULT_PROFILE} --platform {DEFAULT_PLATFORM}"
            ),
            risk_tier=1,
            executable_now=True,
            approval_required=False,
        )
    return decision(
        category="amendment",
        action="inspect-amendment",
        target=amendment_id,
        summary=f"Continue or disposition amendment {amendment_id}; no dependency-eligible task is READY.",
        command=f"python tools/taskctl.py --file planning/backlog.yaml amendment status {amendment_id}",
        risk_tier=0,
        executable_now=amendment_id != "unknown-amendment",
        approval_required=False,
    )


def wave_decision(
    data: dict[str, Any],
    capabilities: dict[str, dict[str, Any]],
    slices: dict[str, dict[str, Any]],
    tasks: dict[str, dict[str, Any]],
    gates: dict[str, dict[str, Any]],
    program: dict[str, Any],
    *,
    profile: str,
    platform: str,
) -> dict[str, Any]:
    wave_id = str(program.get("current_wave") or "")
    waves = taskctl.wave_map(data)
    active = taskctl.active_wave_campaigns(data)
    if active:
        wave = active[0]
        wave_id = str(wave["id"])
        ready = taskctl.ready_tasks_in_wave(data, wave, capabilities, slices, tasks, gates, profile, platform)
        if ready:
            task_id = str(ready[0]["id"])
            return decision(
                category="task",
                action="claim-wave-task",
                target=task_id,
                summary=f"Claim the next dependency-eligible task in active Wave {wave_id}.",
                command=(
                    f"python tools/taskctl.py --file planning/backlog.yaml claim {task_id} --agent <agent> "
                    "--branch <codex-branch> --base-sha <HEAD> --worktree <absolute-repository-path> "
                    f"--profile {profile} --platform {platform}"
                ),
                risk_tier=1,
                executable_now=True,
                approval_required=False,
            )
        if taskctl.wave_complete(wave_id, slices, tasks, data):
            return decision(
                category="wave",
                action="qualify-wave",
                target=wave_id,
                summary=f"Run Wave-exit qualification and prepare commit-bound evidence for {wave_id}.",
                command=None,
                risk_tier=1,
                executable_now=True,
                approval_required=False,
            )
        return decision(
            category="wave",
            action="inspect-active-wave",
            target=wave_id,
            summary=f"No task is READY in active Wave {wave_id}; inspect the recorded task or review blocker.",
            command=f"python tools/taskctl.py --file planning/backlog.yaml wave status {wave_id}",
            risk_tier=0,
            executable_now=True,
            approval_required=False,
        )

    wave = waves.get(wave_id, {})
    if (wave.get("approval") or {}).get("status") != "APPROVED":
        return decision(
            category="wave-approval",
            action="review-wave",
            target=wave_id or None,
            summary=f"Review the complete immutable {wave_id} packet before starting execution.",
            command=f"python tools/planctl.py --repo . wave review {wave_id}" if wave_id else None,
            risk_tier=2,
            executable_now=bool(wave_id),
            approval_required=True,
        )
    return decision(
        category="wave",
        action="start-wave",
        target=wave_id or None,
        summary=f"Start the approved {wave_id} campaign with an exact branch, commit, and worktree lease.",
        command=(
            f"python tools/taskctl.py --file planning/backlog.yaml wave start {wave_id} --agent <agent> "
            "--branch <codex-branch> --base-sha <HEAD> --worktree <absolute-repository-path> "
            f"--profile {profile} --platform {platform}"
            if wave_id
            else None
        ),
        risk_tier=1,
        executable_now=bool(wave_id),
        approval_required=False,
    )


def project_next_action(
    data: dict[str, Any],
    capabilities: dict[str, dict[str, Any]],
    slices: dict[str, dict[str, Any]],
    tasks: dict[str, dict[str, Any]],
    gates: dict[str, dict[str, Any]],
    *,
    profile: str,
    platform: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    taskctl.refresh_derived_states(data, capabilities, slices, tasks, gates)
    program = taskctl.global_program_position(data, slices, tasks, gates)
    state = str(program.get("state"))
    if state == "RECOVERY_INTERRUPTED":
        result = recovery_decision(program)
    elif taskctl.active_amendment_campaigns(data) or state == "AMENDMENT_INTERRUPTED":
        result = amendment_decision(data, program)
    elif state == "GATE_PENDING":
        gate = program.get("next_gate") or {}
        gate_id = str(gate.get("id") or "unknown-gate")
        result = decision(
            category="release-gate",
            action="review-gate",
            target=gate_id,
            summary=f"Review prerequisite completion and criterion-linked evidence for {gate_id}.",
            command=f"python tools/taskctl.py --file planning/backlog.yaml gate status {gate_id}",
            risk_tier=2,
            executable_now=True,
            approval_required=True,
        )
    elif state == "COMPLETE":
        result = decision(
            category="complete",
            action="none",
            target=None,
            summary="The governed roadmap is complete.",
            command=None,
            risk_tier=0,
            executable_now=False,
            approval_required=False,
        )
    else:
        result = wave_decision(
            data,
            capabilities,
            slices,
            tasks,
            gates,
            program,
            profile=profile,
            platform=platform,
        )
    program_view = {
        "state": state,
        "currentWave": program.get("current_wave"),
        "blockedWave": program.get("blocked_wave"),
        "nextGate": (program.get("next_gate") or {}).get("id"),
    }
    return result, program_view


def legacy_category(output: str) -> str:
    first = next((line.strip() for line in output.splitlines() if line.strip()), "")
    if first.startswith("STOPPED AT GOVERNANCE RECOVERY"):
        return "recovery-hold"
    if first.startswith("STOPPED AT WAVE AMENDMENT"):
        return "amendment"
    if first.startswith("STOPPED AT RELEASE GATE"):
        return "release-gate"
    if first.startswith("STOPPED AT PRE-WAVE APPROVAL"):
        return "wave-approval"
    if first.startswith("WAVE IMPLEMENTATION COMPLETE") or first.startswith("No READY task in active Wave"):
        return "wave"
    try:
        document = taskctl.yaml.safe_load(output)
    except taskctl.yaml.YAMLError:
        return "unknown"
    if isinstance(document, dict) and document.get("id"):
        return "task"
    if isinstance(document, dict) and document.get("wave"):
        return "wave"
    return "unknown"


def legacy_projection(
    backlog_path: Path,
    indexed: tuple[
        dict[str, Any],
        dict[str, dict[str, Any]],
        dict[str, dict[str, Any]],
        dict[str, dict[str, Any]],
        dict[str, dict[str, Any]],
    ],
    *,
    profile: str,
    platform: str,
) -> dict[str, Any]:
    args = argparse.Namespace(file=str(backlog_path), profile=profile, platform=platform)
    stream = io.StringIO()
    with redirect_stdout(stream):
        taskctl.command_next(args, *indexed)
    output = stream.getvalue().strip()
    first = next((line.strip() for line in output.splitlines() if line.strip()), "")
    return {
        "category": legacy_category(output),
        "summary": first,
        "outputSha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
    }


def command_next(args: argparse.Namespace) -> None:
    if not args.shadow or not args.json_output:
        raise SystemExit("The first governancectl increment is advisory only; use `next --shadow --json`.")
    root = repository_root(args.repo)
    backlog_path = root / "planning" / "backlog.yaml"
    before = backlog_path.read_bytes()
    before_stat = backlog_path.stat()
    indexed = taskctl.load(str(backlog_path))
    projected = fresh_index(indexed[0])
    action, program = project_next_action(
        *projected,
        profile=args.profile,
        platform=args.platform,
    )
    legacy = legacy_projection(
        backlog_path,
        fresh_index(indexed[0]),
        profile=args.profile,
        platform=args.platform,
    )
    after = backlog_path.read_bytes()
    after_stat = backlog_path.stat()
    if before != after or before_stat.st_mtime_ns != after_stat.st_mtime_ns:
        raise SystemExit("Shadow projection changed the canonical backlog; refusing output")
    output = {
        "schemaVersion": SCHEMA_VERSION,
        "documentType": DOCUMENT_TYPE,
        "mode": "shadow",
        "authority": "advisory-only",
        "mutationPerformed": False,
        "source": {
            "path": "planning/backlog.yaml",
            "sha256": hashlib.sha256(before).hexdigest(),
            "schemaValidated": True,
            "unchanged": True,
        },
        "executionTarget": {"profile": args.profile, "platform": args.platform},
        "program": program,
        "decision": action,
        "legacy": legacy,
        "shadowAgreement": {"category": action["category"] == legacy["category"]},
    }
    print(json.dumps(output, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    subparsers = parser.add_subparsers(dest="command", required=True)
    next_parser = subparsers.add_parser("next", help="Project one advisory next action without mutation")
    next_parser.add_argument("--shadow", action="store_true")
    next_parser.add_argument("--json", dest="json_output", action="store_true")
    next_parser.add_argument("--profile", choices=sorted(taskctl.ACTIVE_PROFILES), default=DEFAULT_PROFILE)
    next_parser.add_argument("--platform", choices=sorted(taskctl.PLATFORMS), default=DEFAULT_PLATFORM)
    next_parser.set_defaults(func=command_next)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
