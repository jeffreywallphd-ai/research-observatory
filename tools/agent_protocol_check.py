#!/usr/bin/env python3
"""Validate coding-agent instructions and render an unfamiliar-agent task brief."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

REQUIRED_DOCUMENT_ANCHORS = {
    "AGENTS.md": [
        "## Default execution model",
        "### One pre-Wave approval and one durable campaign",
        "Safest concise start prompt",
        "## Evidence and completion",
        "## Local main integration",
    ],
    "planning/README.md": [
        "## Default planning and execution lifecycle",
        "One pre-Wave approval binds the complete Wave packet",
    ],
    "docs/automation/project-automation-guide.md": [
        "## 2. Wave campaigns",
        "### 2.1 One approval and durable-Wave meaning",
        "## 5. Task and slice execution",
    ],
    "docs/automation/codex-tracking-guide.md": [
        "## Before editing",
        "## Continuous execution",
        "## Evidence",
        "## Independent review",
    ],
}


def load_protocol(repo: Path) -> dict[str, Any]:
    return json.loads((repo / "agent-protocol.json").read_text(encoding="utf-8"))


def validate_protocol(
    repo: Path,
    protocol: dict[str, Any],
    document_overrides: dict[str, str] | None = None,
) -> list[str]:
    errors: list[str] = []
    documents = document_overrides or {}
    for relative, anchors in REQUIRED_DOCUMENT_ANCHORS.items():
        text = documents.get(relative)
        if text is None:
            path = repo / relative
            if not path.is_file():
                errors.append(f"missing agent instruction authority: {relative}")
                continue
            text = path.read_text(encoding="utf-8")
        for anchor in anchors:
            if anchor not in text:
                errors.append(f"{relative} lacks required instruction anchor: {anchor}")

    campaign = protocol.get("campaign", {})
    expected_campaign = {
        "approvalUnit": "complete-wave-packet-at-one-immutable-commit",
        "decisionScope": "exact-wave-binding-decisions; inherited-and-future-decisions-are-nonbinding-context",
        "partialApprovalStartsCampaign": False,
        "executionUnit": "durable-wave-campaign",
        "resumeAfterOrdinaryInterruption": True,
        "routineSliceApprovalPrompts": False,
        "terminalOutcome": "all-wave-slices-approved-full-suite-passed-and-wave-independently-qualified",
    }
    for field, expected in expected_campaign.items():
        if campaign.get(field) != expected:
            errors.append(f"campaign.{field} must be {expected!r}")
    if len(campaign.get("permittedPauseConditions", [])) < 7:
        errors.append("campaign must retain every governed pause condition")

    selection = protocol.get("selection", {})
    if selection.get("scope") != "active-wave-campaign-only":
        errors.append("task selection must remain inside the active Wave campaign")
    if selection.get("eligibleState") != "READY":
        errors.append("only READY tasks may be selected")
    if "taskctl.py" not in selection.get("claimCommand", ""):
        errors.append("the claim protocol must use taskctl")

    scope = protocol.get("scopeControl", {})
    if not scope.get("permitted") or not scope.get("prohibited"):
        errors.append("scope control must state both permitted and prohibited work")
    verification = protocol.get("verification", {})
    expected_verification = {
        "selectionPolicy": "credible-failure-likelihood-and-changed-path-impact",
        "taskDefault": "focused-affected-checks",
        "fullProfileStage": "wave-exit-qualification",
        "completeMatrixStage": "wave-exit-qualification",
        "breadthRationaleRequiredInEvidence": True,
    }
    for field, expected in expected_verification.items():
        if verification.get(field) != expected:
            errors.append(f"verification.{field} must be {expected!r}")
    if len(verification.get("earlyFullProfileConditions", [])) < 4:
        errors.append("verification must retain every governed early full-profile condition")
    if not verification.get("exactCommitRequired"):
        errors.append("verification evidence must be bound to the exact commit")
    completion = protocol.get("completion", {})
    if completion.get("remotePushAuthorized") is not False:
        errors.append("the default protocol cannot authorize a remote push")
    if completion.get("gateBypassAllowed") is not False:
        errors.append("the protocol cannot allow gate bypass")
    required_steps = {
        "criterion-linked-machine-evidence",
        "required-independent-review",
        "clean-tested-fast-forward-to-local-main",
        "slice-end-to-end-evidence-and-independent-review-when-last-task",
        "risk-cluster-integration-checkpoint-when-triggered",
        "continue-next-ready-task-until-wave-exit-qualification",
    }
    if not required_steps.issubset(set(completion.get("orderedSteps", []))):
        errors.append("completion protocol lacks evidence, review, local-main, slice, or continuation steps")
    if len(protocol.get("waveQualification", [])) < 12:
        errors.append("Wave production qualification is incomplete")
    review = protocol.get("reviewPractice", {})
    if (
        review.get("defaultDeepReviewUnit") != "slice"
        or review.get("taskReviewDefault") != "focused-scope-evidence-and-credible-risk-disposition"
        or not review.get("expandedTaskReviewWhen")
    ):
        errors.append("review practice must define focused task disposition, slice-deep review, and risk expansion")
    return errors


def task_brief(task: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    if task.get("status") != "READY":
        raise ValueError(f"task {task.get('id')} is not READY")
    return {
        "taskId": task["id"],
        "permittedScope": {
            "objective": task["objective"],
            "deliverables": task["deliverables"],
            "acceptanceCriteria": task["acceptance_criteria"],
            "dependencies": task["dependencies"],
            "profiles": task["deployment_profiles"],
            "platforms": task["platform_targets"],
            "scopeRules": protocol["scopeControl"],
        },
        "requiredChecks": {
            "profiles": task["verification_profiles"],
            "commands": task["verification_commands"],
            "additionalSources": protocol["verification"]["requiredSources"],
            "selectionPolicy": protocol["verification"]["selectionPolicy"],
            "taskDefault": protocol["verification"]["taskDefault"],
            "fullProfileStage": protocol["verification"]["fullProfileStage"],
        },
        "completionProtocol": protocol["completion"]["orderedSteps"],
        "claimCommandTemplate": protocol["selection"]["claimCommand"],
    }


def find_task(backlog: dict[str, Any], task_id: str) -> dict[str, Any]:
    for capability in backlog["capabilities"]:
        for slice_ in capability["slices"]:
            for task in slice_["tasks"]:
                if task["id"] == task_id:
                    return task
    raise KeyError(task_id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--task", help="Print the permitted scope, checks, and completion protocol for a READY task")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    protocol = load_protocol(repo)
    errors = validate_protocol(repo, protocol)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    if args.task:
        backlog = yaml.safe_load((repo / "planning" / "backlog.yaml").read_text(encoding="utf-8"))
        try:
            brief = task_brief(find_task(backlog, args.task), protocol)
        except (KeyError, ValueError) as exc:
            print(f"ERROR: {exc}")
            return 2
        print(json.dumps(brief, indent=2))
    else:
        print("Agent protocol: pass - one pre-Wave approval and durable Wave execution")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
