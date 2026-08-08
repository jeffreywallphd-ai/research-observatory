#!/usr/bin/env python3
"""Run Trivy and enforce vulnerability, secret, license, and exception policy."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from install_trivy import InstallError, install, scanner_version
from install_trivy import load_contract as load_toolchain_contract

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def load_json_object(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return loaded


def load_policy(repo: Path) -> dict[str, Any]:
    policy = load_json_object(repo / "security-policy.json")
    if policy.get("schemaVersion") != "1.0" or policy.get("documentType") != "software-supply-chain-policy":
        raise ValueError("security-policy.json contract identity is invalid")
    return policy


def finding_key(kind: str, identifier: str, target: str, package: str = "") -> str:
    return "|".join((kind, identifier, target.replace("\\", "/"), package))


def _items(result: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = result.get(key)
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def normalize_reports(reports: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    findings_by_key: dict[str, dict[str, Any]] = {}
    packages_by_key: dict[str, dict[str, str]] = {}
    for report in reports:
        if report.get("SchemaVersion") != 2 or not isinstance(report.get("Results", []), list):
            raise ValueError("Trivy report must use SchemaVersion 2 and contain a Results array")
        for raw_result in report.get("Results", []):
            if not isinstance(raw_result, dict):
                continue
            target = str(raw_result.get("Target", "unknown"))
            package_type = str(raw_result.get("Type", "unknown"))
            for dependency in _items(raw_result, "Packages"):
                name = str(dependency.get("Name", "unknown"))
                version = str(dependency.get("Version", "unknown"))
                key = f"{package_type}|{name}|{version}|{target}"
                packages_by_key[key] = {
                    "ecosystem": package_type,
                    "name": name,
                    "version": version,
                    "relationship": str(dependency.get("Relationship", "unknown")),
                    "target": target,
                }
            for vulnerability in _items(raw_result, "Vulnerabilities"):
                identifier = str(vulnerability.get("VulnerabilityID", "unknown"))
                package_name = str(vulnerability.get("PkgName", "unknown"))
                key = finding_key("vulnerability", identifier, target, package_name)
                findings_by_key[key] = {
                    "key": key,
                    "kind": "vulnerability",
                    "id": identifier,
                    "severity": str(vulnerability.get("Severity", "UNKNOWN")).upper(),
                    "target": target,
                    "package": package_name,
                    "installedVersion": str(vulnerability.get("InstalledVersion", "unknown")),
                    "fixedVersion": str(vulnerability.get("FixedVersion", "")),
                    "title": str(vulnerability.get("Title", "Known dependency vulnerability")),
                }
            for secret in _items(raw_result, "Secrets"):
                identifier = str(secret.get("RuleID", "unknown"))
                start_line = int(secret.get("StartLine", 0) or 0)
                key = finding_key("secret", identifier, target, f"line:{start_line}")
                findings_by_key[key] = {
                    "key": key,
                    "kind": "secret",
                    "id": identifier,
                    "severity": str(secret.get("Severity", "UNKNOWN")).upper(),
                    "target": target,
                    "package": "",
                    "line": start_line,
                    "title": str(secret.get("Title", "Potential committed secret")),
                }
            for issue in _items(raw_result, "Misconfigurations"):
                identifier = str(issue.get("ID", "unknown"))
                key = finding_key("misconfiguration", identifier, target)
                findings_by_key[key] = {
                    "key": key,
                    "kind": "misconfiguration",
                    "id": identifier,
                    "severity": str(issue.get("Severity", "UNKNOWN")).upper(),
                    "target": target,
                    "package": "",
                    "title": str(issue.get("Title", "Security misconfiguration")),
                }
            for license_item in _items(raw_result, "Licenses"):
                identifier = str(license_item.get("Name", "UNKNOWN"))
                package_name = str(license_item.get("PkgName", "unknown"))
                key = finding_key("license", identifier, target, package_name)
                findings_by_key[key] = {
                    "key": key,
                    "kind": "license",
                    "id": identifier,
                    "severity": str(license_item.get("Severity", "UNKNOWN")).upper(),
                    "category": str(license_item.get("Category", "unknown")).lower(),
                    "target": target,
                    "package": package_name,
                    "title": f"{package_name} declares {identifier}",
                }
    return (
        [findings_by_key[key] for key in sorted(findings_by_key)],
        [packages_by_key[key] for key in sorted(packages_by_key)],
    )


def _date(value: Any, field: str) -> date:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date") from exc


def validate_exceptions(
    policy: dict[str, Any],
    contract: dict[str, Any],
    today: date | None = None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    current_date = today or datetime.now(UTC).date()
    errors: list[str] = []
    if contract.get("schemaVersion") != "1.0" or contract.get("documentType") != "software-supply-chain-exceptions":
        errors.append("security-exceptions.json contract identity is invalid")
    records = contract.get("exceptions")
    if not isinstance(records, list):
        return {}, [*errors, "security-exceptions.json exceptions must be an array"]
    maximum_days = int(policy.get("maximumExceptionDays", 0))
    valid: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records):
        prefix = f"exceptions[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{prefix} must be an object")
            continue
        key = record.get("findingKey")
        if not isinstance(key, str) or not key or "*" in key:
            errors.append(f"{prefix}.findingKey must be an exact non-wildcard key")
            continue
        if key in valid:
            errors.append(f"duplicate exception findingKey: {key}")
            continue
        for field in ("reviewedBy", "rationale", "ticket"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                errors.append(f"{prefix}.{field} is required")
        if record.get("status") != "approved":
            errors.append(f"{prefix}.status must be approved")
        reviewed_at: date | None = None
        expires_at: date | None = None
        try:
            reviewed_at = _date(record.get("reviewedAt"), f"{prefix}.reviewedAt")
        except ValueError as exc:
            errors.append(str(exc))
        try:
            expires_at = _date(record.get("expiresAt"), f"{prefix}.expiresAt")
        except ValueError as exc:
            errors.append(str(exc))
        if reviewed_at is not None and expires_at is not None:
            if reviewed_at > current_date:
                errors.append(f"{prefix}.reviewedAt cannot be in the future")
            if expires_at < current_date:
                errors.append(f"{prefix} expired on {expires_at.isoformat()}")
            if expires_at < reviewed_at:
                errors.append(f"{prefix}.expiresAt precedes reviewedAt")
            if expires_at > reviewed_at + timedelta(days=maximum_days):
                errors.append(f"{prefix} exceeds the {maximum_days}-day maximum")
        valid[key] = record
    return valid, errors


def blocking_reason(finding: dict[str, Any], policy: dict[str, Any]) -> str | None:
    kind = finding["kind"]
    if kind in set(policy.get("alwaysBlockingKinds", [])):
        return f"{kind} findings always block release"
    if kind == "license":
        license_policy = policy.get("licensePolicy", {})
        identifier = finding["id"].casefold()
        allowed_ids = {str(value).casefold() for value in license_policy.get("allowedIds", [])}
        denied_ids = {str(value).casefold() for value in license_policy.get("deniedIds", [])}
        category = finding.get("category", "unknown").casefold()
        if identifier in denied_ids:
            return f"license {finding['id']} is explicitly denied"
        if identifier in allowed_ids:
            return None
        if category in {str(value).casefold() for value in license_policy.get("deniedCategories", [])}:
            return f"license category {category} is denied"
        if category not in {str(value).casefold() for value in license_policy.get("allowedCategories", [])}:
            return f"license {finding['id']} is not allowed"
        return None
    if finding["severity"] in set(policy.get("blockingSeverities", [])):
        return f"{finding['severity']} meets the release-blocking threshold"
    return None


def evaluate(
    findings: list[dict[str, Any]],
    policy: dict[str, Any],
    exceptions_contract: dict[str, Any],
    today: date | None = None,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    exceptions, errors = validate_exceptions(policy, exceptions_contract, today=today)
    used_exceptions: set[str] = set()
    evaluated: list[dict[str, Any]] = []
    warnings: list[str] = []
    warning_severities = set(policy.get("warningSeverities", []))
    for finding in findings:
        item = dict(finding)
        reason = blocking_reason(item, policy)
        exception = exceptions.get(item["key"])
        if reason and exception:
            item["disposition"] = "EXCEPTED"
            item["policyReason"] = reason
            item["exceptionTicket"] = exception["ticket"]
            item["exceptionExpiresAt"] = exception["expiresAt"]
            used_exceptions.add(item["key"])
        elif reason:
            item["disposition"] = "BLOCK"
            item["policyReason"] = reason
        elif item["severity"] in warning_severities:
            item["disposition"] = "WARN"
            item["policyReason"] = f"{item['severity']} requires review but does not block"
            warnings.append(item["key"])
        else:
            item["disposition"] = "ALLOW"
            item["policyReason"] = "finding is below threshold or explicitly allowed"
        evaluated.append(item)
    unused = sorted(set(exceptions) - used_exceptions)
    errors.extend(f"approved exception does not match a current blocking finding: {key}" for key in unused)
    return evaluated, errors, warnings


def trivy_commands(
    repo: Path, executable: Path, policy: dict[str, Any], temporary: Path
) -> list[tuple[list[str], Path]]:
    scan = policy["scan"]
    cache = repo / ".local" / "cache" / "trivy"
    controlled_config = temporary / "trivy.yaml"
    controlled_ignore = temporary / ".trivyignore"
    controlled_config.write_text("{}\n", encoding="utf-8", newline="\n")
    controlled_ignore.write_text("", encoding="utf-8", newline="\n")
    severities = "UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL"
    common = [
        str(executable),
        "--cache-dir",
        str(cache),
        "--quiet",
        "--config",
        str(controlled_config),
    ]
    source_report = temporary / "source.json"
    source = [
        *common,
        "fs",
        "--format",
        "json",
        "--output",
        str(source_report),
        "--scanners",
        ",".join(scan["sourceScanners"]),
        "--severity",
        severities,
        "--secret-config",
        str(repo / "trivy-secret.yaml"),
        "--timeout",
        "10m",
        "--ignorefile",
        str(controlled_ignore),
    ]
    for directory in scan["skipDirectories"]:
        source.extend(("--skip-dirs", directory))
    source.append(str(repo))

    dependency_report = temporary / "dependencies.json"
    dependencies = [
        *common,
        "fs",
        "--format",
        "json",
        "--output",
        str(dependency_report),
        "--scanners",
        ",".join(scan["dependencyScanners"]),
        "--severity",
        severities,
        "--timeout",
        "10m",
        "--ignorefile",
        str(controlled_ignore),
    ]
    for directory in scan["skipDirectories"]:
        dependencies.extend(("--skip-dirs", directory))
    dependencies.append(str(repo))
    commands = [(source, source_report), (dependencies, dependency_report)]
    for index, relative in enumerate(scan.get("environmentTargets", [])):
        target = repo / relative
        if not target.is_dir():
            continue
        report = temporary / f"environment-{index}.json"
        command = [
            *common,
            "rootfs",
            "--format",
            "json",
            "--output",
            str(report),
            "--scanners",
            ",".join(scan["dependencyScanners"]),
            "--severity",
            severities,
            "--timeout",
            "10m",
            "--ignorefile",
            str(controlled_ignore),
            str(target),
        ]
        commands.append((command, report))
    return commands


def run_trivy(
    repo: Path,
    policy: dict[str, Any],
    runner: CommandRunner = subprocess.run,
) -> tuple[list[dict[str, Any]], str]:
    executable = install(repo)
    pinned_version = load_toolchain_contract(repo)["scanner"]["version"]
    actual_version = scanner_version(executable)
    if actual_version != pinned_version:
        raise InstallError(f"Trivy {actual_version or 'unknown'} is unsupported; expected {pinned_version}")
    temporary_root = repo / ".local" / "tmp"
    temporary_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="security-scan-", dir=temporary_root))
    reports: list[dict[str, Any]] = []
    controlled_environment = {key: value for key, value in os.environ.items() if not key.upper().startswith("TRIVY_")}
    try:
        for command, report_path in trivy_commands(repo, executable, policy, temporary):
            completed = runner(
                command,
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
                env=controlled_environment,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    f"Trivy failed with exit {completed.returncode}; "
                    "scanner output was withheld because it may contain secrets"
                )
            reports.append(load_json_object(report_path))
    finally:
        shutil.rmtree(temporary)
    return reports, pinned_version


def write_report(repo: Path, destination: Path | None, report: dict[str, Any]) -> None:
    if destination is None:
        return
    path = destination if destination.is_absolute() else repo / destination
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--input-report", action="append", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    try:
        policy = load_policy(repo)
        exceptions = load_json_object(repo / policy["exceptionsPath"])
        if args.input_report:
            reports = [load_json_object(path if path.is_absolute() else repo / path) for path in args.input_report]
            scanner = "fixture"
        else:
            reports, scanner = run_trivy(repo, policy)
        findings, packages = normalize_reports(reports)
        evaluated, policy_errors, warnings = evaluate(findings, policy, exceptions)
        blockers = [item for item in evaluated if item["disposition"] == "BLOCK"]
        status = "PASS" if not blockers and not policy_errors else "FAIL"
        report = {
            "schemaVersion": "1.0",
            "documentType": "software-supply-chain-report",
            "generatedAt": datetime.now(UTC).isoformat(),
            "status": status,
            "scannerVersion": scanner,
            "summary": {
                "packages": len(packages),
                "findings": len(evaluated),
                "blocking": len(blockers),
                "excepted": sum(item["disposition"] == "EXCEPTED" for item in evaluated),
                "warnings": len(warnings),
                "policyErrors": len(policy_errors),
            },
            "packages": packages,
            "findings": evaluated,
            "policyErrors": policy_errors,
        }
    except (OSError, KeyError, ValueError, json.JSONDecodeError, InstallError, RuntimeError) as exc:
        report = {
            "schemaVersion": "1.0",
            "documentType": "software-supply-chain-report",
            "generatedAt": datetime.now(UTC).isoformat(),
            "status": "ERROR",
            "failureCause": str(exc),
            "summary": {},
            "packages": [],
            "findings": [],
            "policyErrors": [str(exc)],
        }
        print(f"ERROR: {exc}", file=sys.stderr)
        write_report(repo, args.report, report)
        return 2
    write_report(repo, args.report, report)
    for error in report["policyErrors"]:
        print(f"ERROR: {error}")
    for finding in blockers:
        print(f"BLOCK: {finding['key']} - {finding['policyReason']}")
    print(
        f"Software supply chain: {report['status']} - {len(packages)} packages, "
        f"{len(evaluated)} findings, {len(blockers)} blocking"
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
