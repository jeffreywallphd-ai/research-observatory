#!/usr/bin/env python3
"""Run composable repository verification profiles with machine-readable results."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from collections.abc import Callable
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from typing import Any

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
Clock = Callable[[], float]
FULL_COMMIT = re.compile(r"^[0-9a-f]{40}$")
CONTROLLED_GATE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
POLICY_KEYS = {
    "affectedDeferredOwners",
    "schemaVersion",
    "documentType",
    "gateBoundCommandIds",
    "rules",
    "unknownPathFallback",
    "waveExitProfiles",
}
RULE_KEYS = {"id", "patterns", "commands", "rationaleCode", "safetySensitive"}
BROAD_TASK_COMMAND_IDS = (
    "foundation:benchmark-registry",
    "foundation:unit",
    "desktop:performance",
    "data:project-lifecycle-performance",
    "data:storage-maintenance-performance",
)


def load_contract(repo: Path) -> dict[str, Any]:
    return json.loads((repo / "verification-profiles.json").read_text(encoding="utf-8"))


def load_selection_policy(repo: Path) -> dict[str, Any]:
    return json.loads((repo / "verification/affected-selection.json").read_text(encoding="utf-8"))


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


def canonical_inventory_sha256(contract: dict[str, Any]) -> str:
    inventory = {"commands": contract.get("commands"), "profiles": contract.get("profiles")}
    payload = json.dumps(inventory, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_selection_policy(policy: dict[str, Any], contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(policy, dict):
        return ["affected-selection policy must be an object"]
    if set(policy) != POLICY_KEYS:
        errors.append(f"affected-selection policy keys must be exactly {sorted(POLICY_KEYS)}")
    if policy.get("schemaVersion") != "1.0":
        errors.append("affected-selection policy schemaVersion must be 1.0")
    if policy.get("documentType") != "affected-verification-selection-policy":
        errors.append("affected-selection policy documentType is invalid")
    rules = policy.get("rules")
    seen_ids: set[str] = set()
    seen_patterns: set[str] = set()
    if not isinstance(rules, list) or not rules:
        errors.append("affected-selection policy requires ordered rules")
        rules = []
    for index, rule in enumerate(rules):
        label = f"affected-selection rule {index}"
        if not isinstance(rule, dict):
            errors.append(f"{label} must be an object")
            continue
        if set(rule) != RULE_KEYS:
            errors.append(f"{label} keys must be exactly {sorted(RULE_KEYS)}")
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", rule_id):
            errors.append(f"{label} has an invalid id")
        elif rule_id in seen_ids:
            errors.append(f"duplicate affected-selection rule id {rule_id!r}")
        else:
            seen_ids.add(rule_id)
        rationale = rule.get("rationaleCode")
        if not isinstance(rationale, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", rationale):
            errors.append(f"{label} has an invalid rationaleCode")
        if not isinstance(rule.get("safetySensitive"), bool):
            errors.append(f"{label} safetySensitive must be boolean")
        patterns = rule.get("patterns")
        if (
            not isinstance(patterns, list)
            or not patterns
            or not all(isinstance(item, str) and item for item in patterns)
        ):
            errors.append(f"{label} requires non-empty string patterns")
            patterns = []
        for pattern in patterns:
            pure = PurePosixPath(pattern)
            if "\\" in pattern or pattern.startswith("/") or re.match(r"^[A-Za-z]:", pattern) or ".." in pure.parts:
                errors.append(f"{label} has unsafe pattern {pattern!r}")
            if pattern in seen_patterns:
                errors.append(f"duplicate affected-selection pattern {pattern!r}")
            seen_patterns.add(pattern)
        commands = rule.get("commands")
        if not isinstance(commands, list) or not commands or not all(isinstance(item, str) for item in commands):
            errors.append(f"{label} requires non-empty string commands")
            commands = []
        if len(commands) != len(set(commands)):
            errors.append(f"{label} command IDs must be unique")
        for command_id in commands:
            if command_id not in contract.get("commands", {}):
                errors.append(f"{label} references unknown command {command_id!r}")
    fallback = policy.get("unknownPathFallback")
    if not isinstance(fallback, dict) or set(fallback) != {"strategy", "rationaleCode"}:
        errors.append("unknownPathFallback must contain only strategy and rationaleCode")
    elif fallback.get("strategy") != "full-requested-profiles" or not re.fullmatch(
        r"[a-z0-9][a-z0-9-]*", str(fallback.get("rationaleCode") or "")
    ):
        errors.append("unknownPathFallback is invalid")
    deferred_owners = policy.get("affectedDeferredOwners")
    if deferred_owners != ["W1-exit"]:
        errors.append("affectedDeferredOwners must authorize exactly W1-exit")
    elif not all(CONTROLLED_GATE.fullmatch(owner) for owner in deferred_owners):
        errors.append("affectedDeferredOwners contains an invalid gate identifier")
    expected_gate_bound = [
        "desktop:performance",
        "data:project-lifecycle-performance",
        "data:storage-maintenance-performance",
    ]
    gate_bound = policy.get("gateBoundCommandIds")
    if not isinstance(gate_bound, dict) or set(gate_bound) != {"W1-exit"}:
        errors.append("gateBoundCommandIds must define exactly W1-exit")
    elif gate_bound.get("W1-exit") != expected_gate_bound:
        errors.append(f"W1-exit gate-bound command IDs must be exactly {expected_gate_bound}")
    else:
        for command_id in gate_bound["W1-exit"]:
            if command_id not in contract.get("commands", {}):
                errors.append(f"W1-exit references unknown gate-bound command {command_id!r}")
    wave_profiles = policy.get("waveExitProfiles")
    if not isinstance(wave_profiles, dict) or set(wave_profiles) != {"W1"}:
        errors.append("waveExitProfiles must define exactly W1")
    else:
        expected_w1 = ["ai", "data", "desktop", "e2e-local", "foundation", "graph", "security-local", "service"]
        if wave_profiles.get("W1") != expected_w1:
            errors.append(f"W1 Wave-exit profiles must be exactly {expected_w1}")
        for profile_name in wave_profiles.get("W1") or []:
            profile = contract.get("profiles", {}).get(profile_name)
            if not isinstance(profile, dict) or not profile.get("enabled", True):
                errors.append(f"W1 Wave-exit profile {profile_name!r} must exist and be enabled")
    return errors


def active_profile_commands(
    repo: Path,
    contract: dict[str, Any],
    profile_name: str,
) -> tuple[list[str], list[dict[str, str]]]:
    command_ids = expand_profile(contract, profile_name)
    skipped_optional: list[dict[str, str]] = []
    profile = contract["profiles"][profile_name]
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
    return command_ids, skipped_optional


def full_profile_advisory(repo: Path, contract: dict[str, Any], profile_names: list[str]) -> str | None:
    """Describe the breadth of a direct full-profile run without blocking it."""
    command_ids: list[str] = []
    for profile_name in profile_names:
        profile = contract["profiles"].get(profile_name)
        if not isinstance(profile, dict) or not profile.get("enabled", True):
            continue
        active, _ = active_profile_commands(repo, contract, profile_name)
        command_ids.extend(command_id for command_id in active if command_id not in command_ids)
    if not command_ids:
        return None
    broad = [command_id for command_id in BROAD_TASK_COMMAND_IDS if command_id in command_ids]
    broad_summary = f" Notable broad commands: {', '.join(broad)}." if broad else ""
    return (
        "ADVISORY: Direct --profile mode runs the complete qualification inventory for the requested "
        f"enabled profile(s) ({len(command_ids)} active commands).{broad_summary} Ordinary task work should "
        "run focused risk-selected checks or preview Git-derived affected selection first. This advisory does "
        "not block execution."
    )


def _canonical_command_order(contract: dict[str, Any], command_ids: set[str]) -> list[str]:
    return [command_id for command_id in contract["commands"] if command_id in command_ids]


def _normalized_profiles(contract: dict[str, Any], profile_names: list[str]) -> list[str]:
    requested = set(profile_names)
    unknown = sorted(requested - set(contract["profiles"]))
    if unknown:
        raise ValueError(f"unknown verification profile(s): {', '.join(unknown)}")
    disabled = sorted(name for name in requested if not contract["profiles"][name].get("enabled", True))
    if disabled:
        raise ValueError(f"release-gated verification profile(s) cannot be selected: {', '.join(disabled)}")
    return [name for name in contract["profiles"] if name in requested]


def _profile_inventory(
    repo: Path,
    contract: dict[str, Any],
    profile_names: list[str],
) -> tuple[list[str], set[str], list[dict[str, str]]]:
    active: set[str] = set()
    declared: set[str] = set()
    skipped_by_id: dict[str, dict[str, str]] = {}
    for profile_name in profile_names:
        command_ids, skipped = active_profile_commands(repo, contract, profile_name)
        active.update(command_ids)
        declared.update(expand_profile(contract, profile_name))
        declared.update(item["command"] for item in contract["profiles"][profile_name].get("optionalCommands", []))
        for item in skipped:
            skipped_by_id.setdefault(item["command"], item)
    ordered_active = _canonical_command_order(contract, active)
    ordered_skipped = [
        skipped_by_id[item] for item in contract["commands"] if item in skipped_by_id and item not in active
    ]
    return ordered_active, declared, ordered_skipped


def normalize_changed_paths(paths: list[str]) -> list[str]:
    normalized: set[str] = set()
    for raw in paths:
        if not isinstance(raw, str) or not raw or not raw.strip() or raw != raw.strip():
            raise ValueError("affected Git paths must be non-empty normalized strings")
        if (
            "\\" in raw
            or raw.startswith("/")
            or re.match(r"^[A-Za-z]:", raw)
            or any(ord(character) < 32 for character in raw)
        ):
            raise ValueError(f"unsafe affected Git path: {raw!r}")
        pure = PurePosixPath(raw)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise ValueError(f"unsafe affected Git path: {raw!r}")
        canonical = pure.as_posix()
        if canonical != raw:
            raise ValueError(f"affected Git path is not canonical POSIX form: {raw!r}")
        normalized.add(canonical)
    if not normalized:
        raise ValueError("affected selection requires a non-empty Git-derived changed-path set")
    return sorted(normalized)


def _resolve_git_commit(repo: Path, revision: str, *, allow_head: bool) -> str:
    if (revision != "HEAD" or not allow_head) and not FULL_COMMIT.fullmatch(revision):
        raise ValueError("affected revisions must be full 40-character lowercase commits")
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", f"{revision}^{{commit}}"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    resolved = (completed.stdout or "").strip()
    if completed.returncode != 0 or not FULL_COMMIT.fullmatch(resolved):
        diagnostic = (completed.stderr or completed.stdout or "unknown revision").strip()
        raise ValueError(f"cannot resolve affected revision {revision!r}: {diagnostic}")
    return resolved


def changed_paths_from_git(repo: Path, base: str, head: str = "HEAD") -> tuple[str, str, list[str]]:
    base_commit = _resolve_git_commit(repo, base, allow_head=False)
    head_commit = _resolve_git_commit(repo, head, allow_head=True)
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base_commit, head_commit],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if ancestry.returncode != 0:
        raise ValueError("affected base must be an ancestor of the affected head")
    changed = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", "-z", base_commit, head_commit, "--"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if changed.returncode != 0:
        diagnostic = (changed.stderr or changed.stdout or "git diff failed").strip()
        raise ValueError(f"cannot derive affected paths: {diagnostic}")
    return base_commit, head_commit, normalize_changed_paths(changed.stdout.split("\0")[:-1])


def _controlled_gate(value: str, policy: dict[str, Any]) -> str:
    if not CONTROLLED_GATE.fullmatch(value):
        raise ValueError("deferred gate must be a controlled non-empty identifier such as W1-exit")
    authorized = policy.get("affectedDeferredOwners") or []
    if value not in authorized:
        raise ValueError(f"deferred gate {value!r} is not authorized by the affected-selection policy; choose W1-exit")
    return value


def select_affected_commands(
    repo: Path,
    contract: dict[str, Any],
    policy: dict[str, Any],
    profile_names: list[str],
    changed_paths: list[str],
    deferred_gate: str,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    profiles = _normalized_profiles(contract, profile_names)
    if not profiles:
        raise ValueError("affected selection requires at least one requested profile")
    paths = normalize_changed_paths(changed_paths)
    gate = _controlled_gate(deferred_gate, policy)
    active, declared, skipped = _profile_inventory(repo, contract, profiles)
    active_set = set(active)
    mapped_commands: set[str] = set()
    matched_ids: list[str] = []
    rationale_codes: list[str] = []
    matched_paths: set[str] = set()
    safety_sensitive = False
    for rule in policy["rules"]:
        rule_paths = {path for path in paths if any(fnmatchcase(path, pattern) for pattern in rule["patterns"])}
        if not rule_paths:
            continue
        matched_paths.update(rule_paths)
        mapped_commands.update(rule["commands"])
        matched_ids.append(rule["id"])
        if rule["rationaleCode"] not in rationale_codes:
            rationale_codes.append(rule["rationaleCode"])
        safety_sensitive = safety_sensitive or rule["safetySensitive"]
    unknown_paths = [path for path in paths if path not in matched_paths]
    if unknown_paths:
        fallback_code = policy["unknownPathFallback"]["rationaleCode"]
        if fallback_code not in rationale_codes:
            rationale_codes.append(fallback_code)
    fallback = "safety-sensitive" if safety_sensitive else "unknown-path" if unknown_paths else "none"
    outside_declared = _canonical_command_order(contract, mapped_commands - declared)
    if outside_declared:
        raise ValueError(
            "affected paths map to commands outside the requested profiles; add the owning profile(s): "
            + ", ".join(outside_declared)
        )
    gate_bound = _canonical_command_order(
        contract,
        active_set & set((policy.get("gateBoundCommandIds") or {}).get(gate, [])),
    )
    gate_bound_set = set(gate_bound)
    if fallback != "none":
        selected = _canonical_command_order(contract, active_set - gate_bound_set)
        deferred = gate_bound
        if safety_sensitive:
            rationale = (
                "Safety-sensitive changed paths require the complete requested active profile inventory, except "
                f"gate-bound performance commands retained for {gate}."
            )
        else:
            rationale = (
                "At least one changed path is unknown, so the complete requested active profile inventory is selected, "
                f"except gate-bound performance commands retained for {gate}."
            )
    else:
        selected = _canonical_command_order(contract, (active_set & mapped_commands) - gate_bound_set)
        deferred = _canonical_command_order(contract, active_set - set(selected))
        rationale = (
            f"Matched affected-selection rules; unselected active commands, including governed performance commands, "
            f"are owned by {gate}."
        )
    if set(selected) & set(deferred) or set(selected) | set(deferred) != active_set:
        raise ValueError("affected selection did not partition the requested active command inventory")
    report = {
        "policyVersion": policy["schemaVersion"],
        "changedPaths": paths,
        "requestedProfiles": profiles,
        "selectedCommandIds": selected,
        "deferredCommandIds": deferred,
        "matchedRuleIds": matched_ids,
        "rationaleCodes": rationale_codes,
        "fallback": fallback,
        "unknownPaths": unknown_paths,
        "rationale": rationale,
        "deferredOwner": gate,
        "gateBoundDeferredCommandIds": gate_bound,
        "canonicalInventorySha256": canonical_inventory_sha256(contract),
        "inactiveOptionalCommands": [item["command"] for item in skipped],
    }
    return report, skipped


def resolve_wave_exit_selection(
    repo: Path,
    contract: dict[str, Any],
    policy: dict[str, Any],
    wave: str,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    profiles = (policy.get("waveExitProfiles") or {}).get(wave)
    if not isinstance(profiles, list):
        raise ValueError(f"no governed Wave-exit profile union is defined for {wave}")
    normalized = _normalized_profiles(contract, profiles)
    if set(normalized) != set(profiles):
        raise ValueError(f"{wave} Wave-exit profile union is invalid")
    active, _declared, skipped = _profile_inventory(repo, contract, profiles)
    wave_exit_gate = f"{wave}-exit"
    gate_bound = _canonical_command_order(
        contract,
        set(active) & set((policy.get("gateBoundCommandIds") or {}).get(wave_exit_gate, [])),
    )
    return (
        {
            "policyVersion": policy["schemaVersion"],
            "wave": wave,
            "requestedProfiles": list(profiles),
            "selectedCommandIds": active,
            "deferredCommandIds": [],
            "matchedRuleIds": [],
            "rationaleCodes": ["complete-wave-exit-union"],
            "fallback": "none",
            "rationale": f"{wave} Wave exit executes the complete governed active profile union once.",
            "deferredOwner": None,
            "gateBoundSelectedCommandIds": gate_bound,
            "canonicalInventorySha256": canonical_inventory_sha256(contract),
            "inactiveOptionalCommands": [item["command"] for item in skipped],
        },
        skipped,
    )


def resolve_argv(argv: list[str], repo: Path) -> list[str]:
    replacements = {"{python}": sys.executable, "{repo}": str(repo)}
    return [replacements.get(item, item) for item in argv]


def execute_command_set(
    repo: Path,
    contract: dict[str, Any],
    label: str,
    description: str,
    command_ids: list[str],
    skipped_optional: list[dict[str, str]],
    runner: CommandRunner = subprocess.run,
    clock: Clock = time.monotonic,
) -> tuple[int, dict[str, Any]]:
    started = clock()
    results: list[dict[str, Any]] = []
    status = "PASS"
    failure_cause: str | None = None
    exit_code = 0
    for command_id in command_ids:
        argv = resolve_argv(contract["commands"][command_id]["argv"], repo)
        printable = subprocess.list2cmdline(argv)
        print(f"RUN [{label}/{command_id}] {printable}", flush=True)
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
        "profile": label,
        "description": description,
        "status": status,
        "durationSeconds": round(total, 3),
        "failureCause": failure_cause,
        "commands": results,
        "skippedOptionalCommands": skipped_optional,
    }
    print(f"Verification profile {label}: {status} ({total:.2f}s)")
    return exit_code, result


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

    command_ids, skipped_optional = active_profile_commands(repo, contract, profile_name)
    return execute_command_set(
        repo,
        contract,
        profile_name,
        profile["description"],
        command_ids,
        skipped_optional,
        runner=runner,
        clock=clock,
    )


def _write_report(repo: Path, report_path: Path, aggregate: dict[str, Any]) -> None:
    target = report_path if report_path.is_absolute() else repo / report_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(aggregate, indent=2) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--affected-base")
    parser.add_argument("--affected-head")
    parser.add_argument("--deferred-gate")
    parser.add_argument("--selection-only", action="store_true")
    parser.add_argument("--wave-exit")
    args = parser.parse_args()
    affected_mode = args.affected_base is not None
    if args.list and any((affected_mode, args.affected_head, args.deferred_gate, args.selection_only, args.wave_exit)):
        parser.error("--list cannot be combined with affected-selection or Wave-exit options")
    if args.affected_head is not None and not affected_mode:
        parser.error("--affected-head requires --affected-base")
    if affected_mode and args.wave_exit:
        parser.error("--wave-exit cannot be combined with affected selection")
    if args.wave_exit and args.profile:
        parser.error("--wave-exit uses its governed profile union and cannot be narrowed with --profile")
    if args.deferred_gate and not affected_mode:
        parser.error("--deferred-gate is valid only with --affected-base")
    if affected_mode and not args.deferred_gate:
        parser.error("--deferred-gate is required with --affected-base")
    if args.selection_only and not (affected_mode or args.wave_exit):
        parser.error("--selection-only requires --affected-base or --wave-exit")
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
    if not args.profile and not args.wave_exit:
        parser.error("--profile is required unless --list is used")

    if affected_mode or args.wave_exit:
        try:
            policy = load_selection_policy(repo)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: cannot load affected-selection policy: {exc}", file=sys.stderr)
            return 2
        policy_errors = validate_selection_policy(policy, contract)
        if policy_errors:
            for error in policy_errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 2
        try:
            if affected_mode:
                base_commit, head_commit, paths = changed_paths_from_git(
                    repo,
                    args.affected_base,
                    args.affected_head or "HEAD",
                )
                selection, skipped_optional = select_affected_commands(
                    repo,
                    contract,
                    policy,
                    args.profile,
                    paths,
                    args.deferred_gate,
                )
                selection = {
                    "baseCommit": base_commit,
                    "headCommit": head_commit,
                    **selection,
                }
                mode = "affected"
                label = "affected"
                description = "Deterministic Git-derived affected verification selection."
            else:
                selection, skipped_optional = resolve_wave_exit_selection(repo, contract, policy, args.wave_exit)
                mode = "wave-exit"
                label = f"wave-exit:{args.wave_exit}"
                description = f"Complete governed {args.wave_exit} Wave-exit verification union."
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

        selection_reports: list[dict[str, Any]] = []
        overall_exit = 0
        if not args.selection_only:
            overall_exit, execution = execute_command_set(
                repo,
                contract,
                label,
                description,
                selection["selectedCommandIds"],
                skipped_optional,
            )
            selection_reports.append(execution)
        aggregate = {
            "schemaVersion": "1.1",
            "documentType": "verification-run-report",
            "mode": mode,
            "status": "PASS" if overall_exit == 0 else "FAIL",
            "selectionOnly": bool(args.selection_only),
            "selection": selection,
            "profiles": selection_reports,
        }
        if args.report:
            _write_report(repo, args.report, aggregate)
        elif args.selection_only:
            print(json.dumps(aggregate, indent=2))
        return overall_exit

    advisory = full_profile_advisory(repo, contract, args.profile)
    if advisory:
        print(advisory, file=sys.stderr)

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
        _write_report(repo, args.report, aggregate)
    return overall_exit


if __name__ == "__main__":
    raise SystemExit(main())
