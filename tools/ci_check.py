#!/usr/bin/env python3
"""Validate the least-privilege, pinned continuous-integration contract."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def load_policy(repo: Path) -> dict[str, Any]:
    return json.loads((repo / "ci-policy.json").read_text(encoding="utf-8"))


def load_workflow(text: str) -> dict[str, Any]:
    loaded = yaml.load(text, Loader=yaml.BaseLoader)
    if not isinstance(loaded, dict):
        raise ValueError("workflow root must be a mapping")
    return loaded


def validate_ci(repo: Path, workflow_text: str | None = None) -> list[str]:
    repo = repo.resolve()
    errors: list[str] = []
    try:
        policy = load_policy(repo)
        if workflow_text is None:
            workflow_text = (repo / policy["workflowPath"]).read_text(encoding="utf-8")
        workflow = load_workflow(workflow_text)
    except (OSError, KeyError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        return [f"Cannot load CI contract: {exc}"]

    if policy.get("schemaVersion") != "1.0":
        errors.append("ci-policy.json must use schemaVersion 1.0")
    triggers = workflow.get("on")
    if not isinstance(triggers, dict) or set(triggers) != {"pull_request", "push", "workflow_dispatch"}:
        errors.append("CI triggers must be exactly pull_request, push, and workflow_dispatch")
    elif triggers.get("push", {}).get("branches") != ["main"]:
        errors.append("CI push trigger must be limited to main")
    if workflow.get("permissions") != {"contents": "read"}:
        errors.append("CI root permissions must be exactly contents: read")
    concurrency = workflow.get("concurrency")
    if not isinstance(concurrency, dict) or concurrency.get("cancel-in-progress") != "true":
        errors.append("CI concurrency must cancel superseded runs")
    if workflow.get("defaults", {}).get("run", {}).get("shell") != "pwsh":
        errors.append("CI default shell must be pwsh")

    lowered = workflow_text.lower()
    forbidden = {
        "pull_request_target": "pull_request_target is forbidden",
        "secrets.": "production or repository secrets are forbidden",
        "github.token": "the implicit GitHub token must not be consumed",
        "write-all": "write-all permissions are forbidden",
    }
    for fragment, message in forbidden.items():
        if fragment in lowered:
            errors.append(message)
    if re.search(r"\bsecrets\s*(?:\.|\[)", workflow_text, flags=re.IGNORECASE):
        message = "production or repository secrets are forbidden"
        if message not in errors:
            errors.append(message)

    allowed_actions = policy.get("allowedActions", {})
    for action, specification in allowed_actions.items():
        if not SHA_PATTERN.fullmatch(str(specification.get("sha", ""))):
            errors.append(f"policy action {action} must use a full lowercase commit SHA")

    jobs = workflow.get("jobs")
    expected_jobs = policy.get("jobs", {})
    if not isinstance(jobs, dict):
        return [*errors, "CI workflow jobs must be a mapping"]
    if set(jobs) != set(expected_jobs):
        errors.append(f"CI jobs must be exactly {sorted(expected_jobs)}; found {sorted(jobs)}")

    artifact_names: set[str] = set()
    for job_id, job_policy in expected_jobs.items():
        job = jobs.get(job_id)
        if not isinstance(job, dict):
            continue
        if job.get("runs-on") != policy.get("runner"):
            errors.append(f"job {job_id} must run on {policy.get('runner')}")
        if "permissions" in job:
            errors.append(f"job {job_id} must not override root permissions")
        steps = job.get("steps")
        if not isinstance(steps, list):
            errors.append(f"job {job_id} steps must be an array")
            continue
        run_text = "\n".join(str(step.get("run", "")) for step in steps if isinstance(step, dict))
        for fragment in job_policy.get("requiredRunFragments", []):
            if fragment not in run_text:
                errors.append(f"job {job_id} is missing required command fragment {fragment!r}")

        uploads: list[dict[str, Any]] = []
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                errors.append(f"job {job_id} step {index} must be a mapping")
                continue
            uses = step.get("uses")
            if uses:
                action, separator, reference = str(uses).partition("@")
                specification = allowed_actions.get(action)
                if not separator or specification is None:
                    errors.append(f"job {job_id} uses unapproved action {uses}")
                elif reference != specification.get("sha"):
                    errors.append(f"job {job_id} action {action} is not pinned to the approved commit SHA")
                if action == "actions/checkout" and step.get("with", {}).get("persist-credentials") != "false":
                    errors.append(f"job {job_id} checkout must disable credential persistence")
                if action == "actions/upload-artifact":
                    uploads.append(step)
        if len(uploads) != 1:
            errors.append(f"job {job_id} must have exactly one artifact upload step")
            continue
        upload = uploads[0]
        upload_with = upload.get("with", {})
        if upload.get("if") != "always()":
            errors.append(f"job {job_id} artifact upload must run with always()")
        if upload_with.get("path") != job_policy.get("artifactPath"):
            errors.append(f"job {job_id} artifact path does not match ci-policy.json")
        if upload_with.get("retention-days") != str(policy.get("artifactRetentionDays")):
            errors.append(f"job {job_id} artifact retention does not match ci-policy.json")
        if upload_with.get("if-no-files-found") != "warn" or upload_with.get("include-hidden-files") != "false":
            errors.append(f"job {job_id} artifact handling must warn on absence and exclude hidden files")
        artifact_name = str(upload_with.get("name", ""))
        if "github.run_id" not in artifact_name or "github.run_attempt" not in artifact_name:
            errors.append(f"job {job_id} artifact name must be unique per run attempt")
        if artifact_name in artifact_names:
            errors.append(f"job {job_id} artifact name duplicates another job")
        artifact_names.add(artifact_name)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()
    errors = validate_ci(Path(args.repo))
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Continuous integration contract: pass - pinned, least privilege, retained evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
