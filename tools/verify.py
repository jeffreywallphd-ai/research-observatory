#!/usr/bin/env python3
"""Run composable repository verification profiles with machine-readable results."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
Clock = Callable[[], float]


def load_contract(repo: Path) -> dict[str, Any]:
    return json.loads((repo / "verification-profiles.json").read_text(encoding="utf-8"))


def validate_contract(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    profiles = contract.get("profiles", {})
    commands = contract.get("commands", {})
    expected_profiles = {
        "foundation",
        "desktop",
        "service",
        "data",
        "documents",
        "search",
        "ai",
        "evidence",
        "graph",
        "novelty",
        "e2e-local",
        "security-local",
        "server",
        "cloud",
    }
    if set(profiles) != expected_profiles:
        errors.append(f"verification profiles must be exactly {sorted(expected_profiles)}; found {sorted(profiles)}")
    for command_id, specification in commands.items():
        argv = specification.get("argv") if isinstance(specification, dict) else None
        if not isinstance(argv, list) or not argv or not all(isinstance(item, str) for item in argv):
            errors.append(f"command {command_id!r} must define a non-empty string argv list")

    def visit(profile_name: str, stack: tuple[str, ...]) -> None:
        if profile_name in stack:
            errors.append(f"profile include cycle: {' -> '.join((*stack, profile_name))}")
            return
        profile = profiles.get(profile_name)
        if not isinstance(profile, dict):
            errors.append(f"unknown included profile: {profile_name}")
            return
        for included in profile.get("includes", []):
            visit(included, (*stack, profile_name))

    for profile_name, profile in profiles.items():
        visit(profile_name, ())
        if not isinstance(profile, dict):
            errors.append(f"profile {profile_name!r} must be an object")
            continue
        if not profile.get("description"):
            errors.append(f"profile {profile_name!r} lacks a description")
        enabled = profile.get("enabled", True)
        if not enabled and not profile.get("blockedReason"):
            errors.append(f"disabled profile {profile_name!r} requires blockedReason")
        for command_id in profile.get("commands", []):
            if command_id not in commands:
                errors.append(f"profile {profile_name!r} references unknown command {command_id!r}")
        for optional in profile.get("optionalCommands", []):
            if not isinstance(optional, dict):
                errors.append(f"profile {profile_name!r} optional commands must be objects")
                continue
            if optional.get("command") not in commands:
                errors.append(
                    f"profile {profile_name!r} optional command references unknown command {optional.get('command')!r}"
                )
            activation_keys = [key for key in ("activationPath", "activationGlob") if optional.get(key)]
            if len(activation_keys) != 1 or not optional.get("installedBy"):
                errors.append(
                    f"profile {profile_name!r} optional command requires exactly one "
                    "activationPath/activationGlob and installedBy"
                )
    return errors


def expand_profile(contract: dict[str, Any], profile_name: str) -> list[str]:
    profiles = contract["profiles"]
    if profile_name not in profiles:
        raise KeyError(profile_name)
    ordered: list[str] = []

    def add(name: str) -> None:
        profile = profiles[name]
        for included in profile.get("includes", []):
            add(included)
        for command_id in profile.get("commands", []):
            if command_id not in ordered:
                ordered.append(command_id)

    add(profile_name)
    return ordered


def resolve_argv(argv: list[str], repo: Path) -> list[str]:
    replacements = {"{python}": sys.executable, "{repo}": str(repo)}
    return [replacements.get(item, item) for item in argv]


def execute_profile(
    repo: Path,
    contract: dict[str, Any],
    profile_name: str,
    runner: CommandRunner = subprocess.run,
    clock: Clock = time.monotonic,
) -> tuple[int, dict[str, Any]]:
    profiles = contract["profiles"]
    if profile_name not in profiles:
        return 2, {
            "profile": profile_name,
            "status": "ERROR",
            "failureCause": f"unknown verification profile; choose one of {', '.join(sorted(profiles))}",
            "commands": [],
        }
    profile = profiles[profile_name]
    if not profile.get("enabled", True):
        return 3, {
            "profile": profile_name,
            "status": "BLOCKED",
            "failureCause": profile["blockedReason"],
            "commands": [],
        }

    started = clock()
    command_ids = expand_profile(contract, profile_name)
    skipped_optional: list[dict[str, str]] = []
    for optional in profile.get("optionalCommands", []):
        if optional.get("activationPath"):
            activation_label = optional["activationPath"]
            active = (repo / activation_label).is_file()
        else:
            activation_label = optional["activationGlob"]
            active = any(repo.glob(activation_label))
        if active:
            if optional["command"] not in command_ids:
                command_ids.append(optional["command"])
        else:
            skipped_optional.append(
                {
                    "command": optional["command"],
                    "reason": f"inactive until {optional['installedBy']} creates {activation_label}",
                }
            )

    results: list[dict[str, Any]] = []
    status = "PASS"
    failure_cause: str | None = None
    exit_code = 0
    for command_id in command_ids:
        argv = resolve_argv(contract["commands"][command_id]["argv"], repo)
        printable = subprocess.list2cmdline(argv)
        print(f"RUN [{profile_name}/{command_id}] {printable}", flush=True)
        command_started = clock()
        try:
            completed = runner(
                argv,
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
            )
            command_exit = completed.returncode
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
        except OSError as exc:
            command_exit = 127
            stdout = ""
            stderr = str(exc)
        duration = clock() - command_started
        if stdout:
            print(stdout, end="" if stdout.endswith("\n") else "\n")
        if stderr:
            print(stderr, end="" if stderr.endswith("\n") else "\n", file=sys.stderr)
        command_status = "PASS" if command_exit == 0 else "FAIL"
        results.append(
            {
                "id": command_id,
                "argv": argv,
                "status": command_status,
                "exitCode": command_exit,
                "durationSeconds": round(duration, 3),
                "stdout": stdout,
                "stderr": stderr,
            }
        )
        print(f"{command_status} [{command_id}] ({duration:.2f}s)")
        if command_exit != 0:
            status = "FAIL"
            exit_code = command_exit if command_exit > 0 else 1
            diagnostic = (stderr or stdout).strip()
            failure_cause = (
                f"{command_id} exited {command_exit}: {diagnostic}"
                if diagnostic
                else f"{command_id} exited {command_exit} without diagnostic output"
            )
            break

    total = clock() - started
    result = {
        "profile": profile_name,
        "description": profile["description"],
        "status": status,
        "durationSeconds": round(total, 3),
        "failureCause": failure_cause,
        "commands": results,
        "skippedOptionalCommands": skipped_optional,
    }
    print(f"Verification profile {profile_name}: {status} ({total:.2f}s)")
    return exit_code, result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    try:
        contract = load_contract(repo)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot load verification profile contract: {exc}", file=sys.stderr)
        return 2
    errors = validate_contract(contract)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2
    if args.list:
        for name, profile in contract["profiles"].items():
            state = "enabled" if profile.get("enabled", True) else "blocked"
            print(f"{name}\t{state}\t{profile['description']}")
        return 0
    if not args.profile:
        parser.error("--profile is required unless --list is used")

    reports: list[dict[str, Any]] = []
    overall_exit = 0
    for profile_name in args.profile:
        exit_code, report = execute_profile(repo, contract, profile_name)
        reports.append(report)
        if report["status"] in {"ERROR", "BLOCKED"}:
            print(
                f"Verification profile {profile_name}: {report['status']} - {report['failureCause']}",
                file=sys.stderr,
            )
        if exit_code != 0 and overall_exit == 0:
            overall_exit = exit_code
    aggregate = {
        "schemaVersion": "1.0",
        "documentType": "verification-run-report",
        "status": "PASS" if overall_exit == 0 else "FAIL",
        "profiles": reports,
    }
    if args.report:
        report_path = args.report if args.report.is_absolute() else repo / args.report
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(aggregate, indent=2) + "\n", encoding="utf-8", newline="\n")
    return overall_exit


if __name__ == "__main__":
    raise SystemExit(main())
