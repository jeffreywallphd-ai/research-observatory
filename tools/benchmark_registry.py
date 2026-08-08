#!/usr/bin/env python3
"""Validate and run the deterministic benchmark and golden-output registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

REGISTRY_PATH = "evaluation/registry.json"
REGISTRY_SCHEMA_PATH = "evaluation/registry.schema.json"
APPROVAL_ROOT = "evaluation/approvals/"
REPORT_ROOT = "artifacts/tmp"
EXECUTOR_KIND = {
    "metadata-json-normalizer-v1": "golden-parsing",
    "json-schema-validation-v1": "contract-validation",
}
TRACKED_METADATA_FIELDS = ("abstract", "authors", "containerTitle", "issued")


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def safe_snapshot(repo: Path, raw_path: Any) -> tuple[Path | None, bytes | None, str | None]:
    if not isinstance(raw_path, str):
        return None, None, "path must be a string"
    pure = PurePosixPath(raw_path)
    if pure.is_absolute() or ".." in pure.parts or "\\" in raw_path:
        return None, None, f"unsafe repository path {raw_path!r}"
    lexical = repo.joinpath(*pure.parts)
    try:
        before = lexical.lstat()
        resolved = lexical.resolve(strict=True)
        resolved.relative_to(repo)
    except (OSError, ValueError) as exc:
        return None, None, f"path does not resolve inside repository: {raw_path}: {exc}"
    if resolved != lexical:
        return None, None, f"path must not be a symbolic link or redirect: {raw_path}"
    if not resolved.is_file():
        return None, None, f"path is not a file: {raw_path}"
    try:
        payload = resolved.read_bytes()
        after = lexical.lstat()
        resolved_after = lexical.resolve(strict=True)
    except OSError as exc:
        return None, None, f"cannot read {raw_path}: {exc}"
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after or resolved_after != resolved:
        return None, None, f"path changed while being read: {raw_path}"
    return resolved, payload, None


def parse_json(payload: bytes, label: str) -> tuple[Any | None, str | None]:
    try:
        return json.loads(payload.decode("utf-8")), None
    except (UnicodeError, json.JSONDecodeError) as exc:
        return None, f"cannot parse {label} as UTF-8 JSON: {exc}"


def registry_schema_errors(registry: Any, schema: Any) -> list[str]:
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        return [f"invalid benchmark registry schema: {exc.message}"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(registry), key=lambda error: [str(part) for part in error.path])
    return [f"registry.{'.'.join(str(part) for part in error.path) or '<root>'}: {error.message}" for error in errors]


def previous_registry_from_git(repo: Path) -> dict[str, Any] | None:
    try:
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--", "evaluation/registry.json", "evaluation/baselines"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        if dirty.returncode != 0:
            return None
        reference = "HEAD" if dirty.stdout.strip() else "HEAD^"
        previous = subprocess.run(
            ["git", "show", f"{reference}:{REGISTRY_PATH}"],
            cwd=repo,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if previous.returncode != 0:
        return None
    try:
        value = json.loads(previous.stdout.decode("utf-8"))
    except UnicodeError, json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def baseline_lineage_errors(current: dict[str, Any], previous: dict[str, Any] | None) -> list[str]:
    errors: list[str] = []
    current_items = {
        item["id"]: item for item in current.get("benchmarks", []) if isinstance(item, dict) and "id" in item
    }
    if previous is None:
        return errors
    previous_items = {
        item["id"]: item for item in previous.get("benchmarks", []) if isinstance(item, dict) and "id" in item
    }
    for removed in sorted(set(previous_items) - set(current_items)):
        errors.append(f"benchmark removal requires a governed deprecation workflow: {removed}")
    for benchmark_id, current_item in current_items.items():
        current_baseline = current_item.get("baseline", {})
        previous_item = previous_items.get(benchmark_id)
        if previous_item is None:
            if current_baseline.get("version") != 1:
                errors.append(f"{benchmark_id}: a new benchmark baseline must start at version 1")
            continue
        previous_baseline = previous_item.get("baseline", {})
        old_hash = previous_item.get("expected", {}).get("sha256")
        new_hash = current_item.get("expected", {}).get("sha256")
        if old_hash == new_hash:
            if current_baseline != previous_baseline:
                errors.append(f"{benchmark_id}: baseline lineage changed without expected-output change")
            continue
        expected_history = [
            *previous_baseline.get("history", []),
            {
                "version": previous_baseline.get("version"),
                "sha256": old_hash,
                "approval": previous_baseline.get("currentApproval"),
            },
        ]
        if current_baseline.get("version") != previous_baseline.get("version", 0) + 1:
            errors.append(f"{benchmark_id}: changed baseline must increment exactly one version")
        if current_baseline.get("history") != expected_history:
            errors.append(f"{benchmark_id}: changed baseline must append the exact previous baseline to history")
        if not current_baseline.get("currentApproval"):
            errors.append(f"{benchmark_id}: changed baseline requires currentApproval")
    return errors


def approval_errors(
    repo: Path,
    assets: dict[str, bytes],
    benchmark_id: str,
    version: int,
    old_hash: str,
    new_hash: str,
    raw_path: Any,
) -> list[str]:
    if not isinstance(raw_path, str) or not raw_path.startswith(APPROVAL_ROOT) or not raw_path.endswith(".json"):
        return [f"{benchmark_id}: approval path must be a JSON file under {APPROVAL_ROOT}"]
    _, payload, path_error = safe_snapshot(repo, raw_path)
    if path_error or payload is None:
        return [f"{benchmark_id}: invalid approval: {path_error}"]
    assets[raw_path] = payload
    approval, parse_error = parse_json(payload, f"approval {raw_path}")
    if parse_error or not isinstance(approval, dict):
        return [f"{benchmark_id}: {parse_error or 'approval must be an object'}"]
    expected = {
        "schemaVersion": "1.0",
        "documentType": "baseline-approval",
        "status": "approved",
        "benchmarkId": benchmark_id,
        "fromVersion": version - 1,
        "toVersion": version,
        "oldSha256": old_hash,
        "newSha256": new_hash,
    }
    errors = [
        f"{benchmark_id}: approval {key} must equal {value!r}"
        for key, value in expected.items()
        if approval.get(key) != value
    ]
    approved_by = approval.get("approvedBy")
    generated_by = approval.get("generatedBy")
    if not isinstance(approved_by, str) or not approved_by.startswith("human:"):
        errors.append(f"{benchmark_id}: approvedBy must use a human: identity")
    if not isinstance(generated_by, str) or not generated_by:
        errors.append(f"{benchmark_id}: generatedBy is required")
    if approved_by == generated_by:
        errors.append(f"{benchmark_id}: baseline generator cannot approve the same baseline")
    if not isinstance(approval.get("rationale"), str) or not approval["rationale"].strip():
        errors.append(f"{benchmark_id}: approval rationale is required")
    approved_at = approval.get("approvedAt")
    try:
        parsed_time = datetime.fromisoformat(approved_at) if isinstance(approved_at, str) else None
    except ValueError:
        parsed_time = None
    if parsed_time is None or parsed_time.tzinfo is None:
        errors.append(f"{benchmark_id}: approvedAt must be a timezone-aware ISO timestamp")
    return errors


def load_registry(repo: Path) -> tuple[dict[str, Any] | None, dict[str, bytes], list[str]]:
    repo = repo.resolve(strict=True)
    assets: dict[str, bytes] = {}
    errors: list[str] = []
    _, registry_payload, registry_path_error = safe_snapshot(repo, REGISTRY_PATH)
    _, schema_payload, schema_path_error = safe_snapshot(repo, REGISTRY_SCHEMA_PATH)
    if registry_path_error or registry_payload is None:
        errors.append(f"benchmark registry: {registry_path_error}")
    if schema_path_error or schema_payload is None:
        errors.append(f"benchmark registry schema: {schema_path_error}")
    if errors:
        return None, assets, errors
    assert registry_payload is not None and schema_payload is not None
    registry, registry_parse_error = parse_json(registry_payload, REGISTRY_PATH)
    schema, schema_parse_error = parse_json(schema_payload, REGISTRY_SCHEMA_PATH)
    if registry_parse_error:
        errors.append(registry_parse_error)
    if schema_parse_error:
        errors.append(schema_parse_error)
    if errors or not isinstance(registry, dict):
        return None, assets, errors or ["benchmark registry must be an object"]
    errors.extend(registry_schema_errors(registry, schema))
    if errors:
        return registry, assets, errors

    benchmarks = registry["benchmarks"]
    ids = [item["id"] for item in benchmarks]
    if len(ids) != len(set(ids)):
        errors.append("benchmark IDs must be unique")
    kinds = {item["kind"] for item in benchmarks}
    if not {"golden-parsing", "contract-validation"} <= kinds:
        errors.append("registry requires at least one golden-parsing and one contract-validation benchmark")
    for item in benchmarks:
        benchmark_id = item["id"]
        if EXECUTOR_KIND[item["executor"]] != item["kind"]:
            errors.append(f"{benchmark_id}: executor is incompatible with benchmark kind")
        path_specs = [item["dataset"], item["expected"], *item["schemas"]]
        for specification in path_specs:
            raw_path = specification["path"]
            _, payload, path_error = safe_snapshot(repo, raw_path)
            if path_error or payload is None:
                errors.append(f"{benchmark_id}: {path_error}")
                continue
            assets[raw_path] = payload
            if sha256(payload) != specification["sha256"]:
                errors.append(f"{benchmark_id}: SHA-256 mismatch for {raw_path}")
        baseline = item["baseline"]
        if baseline["sha256"] != item["expected"]["sha256"]:
            errors.append(f"{benchmark_id}: baseline hash must equal expected-output hash")
        version = baseline["version"]
        history = baseline["history"]
        if len(history) != version - 1:
            errors.append(f"{benchmark_id}: baseline history length must equal version minus one")
        for index, entry in enumerate(history, start=1):
            if entry["version"] != index:
                errors.append(f"{benchmark_id}: baseline history versions must be contiguous from 1")
        if version == 1 and baseline["currentApproval"] is not None:
            errors.append(f"{benchmark_id}: initial baseline must not claim a change approval")
        if history and history[0]["approval"] is not None:
            errors.append(f"{benchmark_id}: version-1 history must not claim a change approval")
        for history_index, entry in enumerate(history[1:], start=1):
            if not entry["approval"]:
                errors.append(f"{benchmark_id}: historical baseline version {entry['version']} requires approval")
                continue
            errors.extend(
                approval_errors(
                    repo,
                    assets,
                    benchmark_id,
                    entry["version"],
                    history[history_index - 1]["sha256"],
                    entry["sha256"],
                    entry["approval"],
                )
            )
        if version > 1:
            if not history:
                errors.append(f"{benchmark_id}: changed baseline requires prior history")
            elif not baseline["currentApproval"]:
                errors.append(f"{benchmark_id}: changed baseline requires currentApproval")
            else:
                if history[-1]["sha256"] == baseline["sha256"]:
                    errors.append(f"{benchmark_id}: baseline version cannot increment without output change")
                errors.extend(
                    approval_errors(
                        repo,
                        assets,
                        benchmark_id,
                        version,
                        history[-1]["sha256"],
                        baseline["sha256"],
                        baseline["currentApproval"],
                    )
                )
        if item["kind"] == "contract-validation" and len(item["schemas"]) != 1:
            errors.append(f"{benchmark_id}: contract benchmark requires exactly one schema")
        if item["kind"] == "golden-parsing" and item["schemas"]:
            errors.append(f"{benchmark_id}: golden parser does not consume a schema")
    errors.extend(baseline_lineage_errors(registry, previous_registry_from_git(repo)))
    return registry, assets, errors


def normalized_issued(raw: Any) -> str | None:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        parts = raw.get("dateParts")
        if isinstance(parts, list) and parts and isinstance(parts[0], list):
            values = parts[0]
            if values and all(isinstance(value, int) for value in values):
                return "-".join(f"{value:02d}" if index else str(value) for index, value in enumerate(values))
    return None


def normalize_metadata(payload: bytes) -> dict[str, Any]:
    source = json.loads(payload.decode("utf-8"))
    seen_dois: dict[str, str] = {}
    normalized: list[dict[str, Any]] = []
    for record in source["records"]:
        authors = []
        for author in record.get("authors", []):
            if author.get("literal"):
                authors.append(author["literal"])
            else:
                authors.append(", ".join(value for value in (author.get("family"), author.get("given")) if value))
        doi = record.get("doi")
        canonical_doi = doi.casefold() if isinstance(doi, str) else None
        duplicate_of = seen_dois.get(canonical_doi) if canonical_doi else None
        if canonical_doi and duplicate_of is None:
            seen_dois[canonical_doi] = record["fixtureId"]
        missing = sorted(field for field in TRACKED_METADATA_FIELDS if not record.get(field))
        normalized.append(
            {
                "id": record["fixtureId"],
                "title": record["title"],
                "authors": authors,
                "issued": normalized_issued(record.get("issued")),
                "containerTitle": record.get("containerTitle"),
                "doi": canonical_doi,
                "duplicateOf": duplicate_of,
                "missingFields": missing,
                "language": record.get("language"),
            }
        )
    return {"schemaVersion": "1.0", "records": normalized}


def validate_contract(dataset: bytes, schema_payload: bytes) -> dict[str, Any]:
    value = json.loads(dataset.decode("utf-8"))
    schema = json.loads(schema_payload.decode("utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    failures = sorted(validator.iter_errors(value), key=lambda error: [str(part) for part in error.path])
    messages = [
        f"{'.'.join(str(part) for part in failure.path) or '<root>'}: {failure.message}" for failure in failures
    ]
    return {
        "schemaId": schema.get("$id"),
        "valid": not messages,
        "errorCount": len(messages),
        "errors": messages,
    }


def run_benchmarks(repo: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    registry, assets, errors = load_registry(repo)
    if errors or registry is None:
        return {
            "schemaVersion": "1.0",
            "documentType": "benchmark-run-report",
            "status": "FAIL",
            "registryVersion": registry.get("registryVersion") if registry else None,
            "errors": errors,
            "results": [],
        }, {}
    results: list[dict[str, Any]] = []
    actuals: dict[str, Any] = {}
    for item in registry["benchmarks"]:
        dataset = assets[item["dataset"]["path"]]
        if item["executor"] == "metadata-json-normalizer-v1":
            actual = normalize_metadata(dataset)
        else:
            schema_payload = assets[item["schemas"][0]["path"]]
            actual = validate_contract(dataset, schema_payload)
        expected, parse_error = parse_json(assets[item["expected"]["path"]], item["expected"]["path"])
        matches = parse_error is None and actual == expected
        actuals[item["id"]] = actual
        results.append(
            {
                "benchmarkId": item["id"],
                "kind": item["kind"],
                "status": "PASS" if matches else "FAIL",
                "datasetSha256": item["dataset"]["sha256"],
                "expectedSha256": item["expected"]["sha256"],
                "actualCanonicalSha256": sha256(canonical_json_bytes(actual)),
                "baselineVersion": item["baseline"]["version"],
                "tolerance": item["tolerance"],
                "metrics": {"exactMatch": 1 if matches else 0},
                "diagnostic": parse_error or (None if matches else "actual output differs from approved baseline"),
            }
        )
    status = "PASS" if all(result["status"] == "PASS" for result in results) else "FAIL"
    return {
        "schemaVersion": "1.0",
        "documentType": "benchmark-run-report",
        "status": status,
        "registryVersion": registry["registryVersion"],
        "errors": [],
        "results": results,
    }, actuals


def safe_output_path(repo: Path, raw_path: Path, allow_directory: bool = False) -> Path:
    destination = raw_path if raw_path.is_absolute() else repo / raw_path
    destination = destination.absolute()
    artifacts_root = (repo / "artifacts").resolve(strict=True)
    report_root_path = repo / REPORT_ROOT
    if not report_root_path.exists():
        report_root_path.mkdir()
    report_root = report_root_path.resolve(strict=True)
    if report_root != artifacts_root / "tmp" or not report_root.is_dir():
        raise ValueError(f"scratch root must not redirect outside repository artifacts: {report_root}")
    candidate = destination if allow_directory else destination.parent
    try:
        candidate.resolve(strict=False).relative_to(report_root)
    except (OSError, ValueError) as exc:
        raise ValueError(f"output must remain under {REPORT_ROOT}: {raw_path}") from exc
    return destination


def atomic_write_json(destination: Path, value: Any) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=f"{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        assert temporary is not None
        os.replace(temporary, destination)
    except OSError:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--proposal-dir", type=Path)
    args = parser.parse_args()
    repo = Path(args.repo).resolve(strict=True)
    report, actuals = run_benchmarks(repo)
    for error in report["errors"]:
        print(f"ERROR: {error}")
    for result in report["results"]:
        print(f"{result['status']} [{result['benchmarkId']}] exactMatch={result['metrics']['exactMatch']}")
    if args.report:
        try:
            atomic_write_json(safe_output_path(repo, args.report), report)
        except (OSError, ValueError) as exc:
            print(f"ERROR: cannot write benchmark report: {exc}")
            return 2
    if args.proposal_dir and report["status"] == "FAIL" and actuals:
        try:
            proposal_dir = safe_output_path(repo, args.proposal_dir, allow_directory=True)
            for benchmark_id, actual in actuals.items():
                atomic_write_json(proposal_dir / f"{benchmark_id}.json", actual)
        except (OSError, ValueError) as exc:
            print(f"ERROR: cannot write benchmark proposals: {exc}")
            return 2
    print(
        f"Benchmark registry: {report['status']} - {len(report['results'])} executed, "
        f"registry v{report['registryVersion']}"
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
