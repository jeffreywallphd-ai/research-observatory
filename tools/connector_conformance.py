"""Static, content-safe conformance checks for connector SDK packages and cases.

This command never imports or executes candidate plugin code. Executable and
security conformance require the separately qualified Windows LPAC worker.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "services" / "core-api" / "src"))

from research_observatory_core.connectors.plugin_broker import PluginBrokerCall  # noqa: E402
from research_observatory_core.connectors.plugin_manifest import (  # noqa: E402
    PluginManifest,
    verify_plugin_package,
)
from research_observatory_core.connectors.plugin_package_intake import (  # noqa: E402
    PluginPackageIntakeProblem,
    inspect_plugin_archive,
)
from research_observatory_core.connectors.plugin_result import PluginWorkerPage  # noqa: E402

_MAX_JSON = 10 * 1024 * 1024
_MAX_DRAFT_FILE = 16 * 1024 * 1024
_MAX_DRAFT_PACKAGE = 64 * 1024 * 1024


class _InvalidJson(ValueError):
    pass


def _unique_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _InvalidJson()
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise _InvalidJson()


def _read_json(path: Path, maximum: int = _MAX_JSON) -> Any:
    try:
        if path.is_symlink() or path.is_junction() or not path.is_file() or path.stat().st_size > maximum:
            raise _InvalidJson()
        raw = path.read_bytes()
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_fields, parse_constant=_reject_constant)
    except OSError, UnicodeError, ValueError, RecursionError:
        raise _InvalidJson() from None


def _escape(part: str | int) -> str:
    return str(part).replace("~", "~0").replace("/", "~1")


def _pointer(*parts: str | int) -> str:
    return "".join("/" + _escape(part) for part in parts)


def _add(violations: list[dict[str, Any]], code: str, pointer: str, case: int | None = None) -> None:
    item: dict[str, Any] = {"code": code, "pointer": pointer}
    if case is not None:
        item["case"] = case
    if item not in violations:
        violations.append(item)


def _model_errors(
    violations: list[dict[str, Any]], error: ValidationError, *, prefix: str, namespace: str, case: int | None = None
) -> None:
    codes = {
        "missing": "REQUIRED",
        "extra_forbidden": "UNKNOWN_FIELD",
        "literal_error": "ENUM_INVALID",
        "string_too_long": "BOUND_EXCEEDED",
        "too_long": "BOUND_EXCEEDED",
        "string_pattern_mismatch": "PATTERN_INVALID",
        "int_type": "TYPE_INVALID",
        "string_type": "TYPE_INVALID",
    }
    for issue in error.errors(include_url=False, include_input=False):
        code = namespace + "_" + codes.get(str(issue["type"]), "INVARIANT_INVALID")
        _add(violations, code, prefix + _pointer(*issue["loc"]), case)


def _draft_manifest(path: Path, violations: list[dict[str, Any]]) -> PluginManifest | None:
    try:
        document = _read_json(path, maximum=64 * 1024)
    except _InvalidJson:
        _add(violations, "MANIFEST_JSON_INVALID", "/manifest")
        return None
    try:
        manifest = PluginManifest.model_validate(document)
    except ValidationError as error:
        _model_errors(violations, error, prefix="/manifest", namespace="MANIFEST")
        return None
    root = path.parent.resolve()
    total = 0
    for index, item in enumerate(manifest.files):
        source = root
        try:
            for part in item.path.split("/"):
                source = source / part
                if source.is_symlink() or source.is_junction():
                    raise OSError
            if not source.resolve(strict=True).is_relative_to(root) or not source.is_file():
                raise OSError
            size = source.stat().st_size
            total += size
            if size > _MAX_DRAFT_FILE or total > _MAX_DRAFT_PACKAGE:
                raise OSError
            digest = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
        except OSError:
            _add(violations, "PACKAGE_FILE_UNAVAILABLE", _pointer("manifest", "files", index, "path"))
            continue
        if digest != item.sha256:
            _add(violations, "PACKAGE_FILE_HASH_MISMATCH", _pointer("manifest", "files", index, "sha256"))
    return manifest


def _signed_package(path: Path, key_id: str, key_file: Path, violations: list[dict[str, Any]]) -> PluginManifest | None:
    try:
        if path.is_symlink() or path.is_junction() or not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
            raise OSError
        raw = path.read_bytes()
    except OSError:
        _add(violations, "PACKAGE_ARCHIVE_UNAVAILABLE", "/package")
        return None
    try:
        if key_file.is_symlink() or key_file.is_junction() or not key_file.is_file():
            raise OSError
        public_key = key_file.read_bytes()
        if len(public_key) != 32:
            raise OSError
    except OSError:
        _add(violations, "PACKAGE_PUBLISHER_KEY_INVALID", "/publisherKey")
        return None
    try:
        inspected = inspect_plugin_archive(raw)
    except PluginPackageIntakeProblem:
        _add(violations, "PACKAGE_ARCHIVE_INVALID", "/package")
        return None
    try:
        verified = verify_plugin_package(
            inspected.manifest_bytes,
            inspected.signature,
            inspected.files,
            {key_id: public_key},
        )
        return verified.manifest
    except ValueError as error:
        known = {
            "plugin-publisher-untrusted": ("PACKAGE_PUBLISHER_UNTRUSTED", "/publisherKey"),
            "plugin-signature-invalid": ("PACKAGE_SIGNATURE_INVALID", "/package/manifest.sig"),
            "plugin-sdk-major-incompatible": ("MANIFEST_SDK_INCOMPATIBLE", "/package/manifest.json/sdkVersion"),
        }
        code, pointer = known.get(str(error), ("PACKAGE_VERIFICATION_INVALID", "/package"))
        _add(violations, code, pointer)
        return None


def _case_shape(document: Any, index: int, violations: list[dict[str, Any]]) -> bool:
    required = {"schemaVersion", "invocationId", "operation", "input", "brokerCall", "brokerResponse", "output"}
    if not isinstance(document, dict):
        _add(violations, "CASE_OBJECT_REQUIRED", "", index)
        return False
    for key in sorted(required - set(document)):
        _add(violations, "CASE_REQUIRED", _pointer(key), index)
    for key in sorted(set(document) - required):
        _add(violations, "CASE_UNKNOWN_FIELD", _pointer(key), index)
    if document.get("schemaVersion") != "1.0":
        _add(violations, "CASE_VERSION_INVALID", "/schemaVersion", index)
    return required <= set(document) and not (set(document) - required) and document.get("schemaVersion") == "1.0"


def _case_local(
    document: dict[str, Any], index: int, manifest: PluginManifest | None, violations: list[dict[str, Any]]
) -> None:
    operation = document["operation"]
    if not isinstance(operation, str):
        _add(violations, "CASE_OPERATION_INVALID", "/operation", index)
        return
    if manifest is not None and operation not in manifest.operations:
        _add(violations, "MANIFEST_OPERATION_UNDECLARED", "/operation", index)
    input_data, call_data = document["input"], document["brokerCall"]
    if not isinstance(input_data, dict):
        _add(violations, "CASE_INPUT_INVALID", "/input", index)
        return
    if not isinstance(call_data, dict):
        _add(violations, "CASE_BROKER_CALL_INVALID", "/brokerCall", index)
        return
    predecessor = input_data.get("previousInvocationId")
    cursor = input_data.get("cursor")
    if (predecessor is None) != (cursor is None):
        _add(violations, "PAGE_PREDECESSOR_CURSOR_PAIR_REQUIRED", "/input/previousInvocationId", index)
    expected_call = {
        "operation": operation,
        **{key: value for key, value in input_data.items() if key != "previousInvocationId"},
    }
    actual_call = {key: value for key, value in call_data.items() if key != "credentialScope"}
    if actual_call != expected_call:
        _add(violations, "CASE_BROKER_CALL_MISMATCH", "/brokerCall", index)
    try:
        PluginBrokerCall.model_validate(call_data)
    except ValidationError as error:
        _model_errors(violations, error, prefix="/brokerCall", namespace="BROKER_CALL", case=index)
    except Exception:
        _add(violations, "CASE_BROKER_CALL_INVALID", "/brokerCall", index)
    output_data = document["output"]
    try:
        page = PluginWorkerPage.model_validate(output_data)
    except ValidationError as error:
        _model_errors(violations, error, prefix="/output", namespace="PAGE", case=index)
        return
    except Exception:
        _add(violations, "PAGE_INVALID", "/output", index)
        return
    if page.invocation_id != document["invocationId"]:
        _add(violations, "PAGE_INVOCATION_MISMATCH", "/output/invocationId", index)
    if page.operation != operation:
        _add(violations, "PAGE_OPERATION_MISMATCH", "/output/operation", index)
    page_size = input_data.get("pageSize")
    if type(page_size) is int and len(page.records) > page_size:
        _add(violations, "PAGE_SIZE_EXCEEDED", "/output/records", index)
    broker_response = document["brokerResponse"]
    observed = broker_response.get("nextCursor") if isinstance(broker_response, dict) else None
    if observed is not None and page.next_cursor is None:
        _add(violations, "PAGE_CURSOR_OMITTED", "/output/nextCursor", index)
    if page.next_cursor is not None:
        if page.next_cursor == cursor:
            _add(violations, "PAGE_CURSOR_NOT_ADVANCING", "/output/nextCursor", index)
        if page.next_cursor != observed:
            _add(violations, "PAGE_CURSOR_UNOBSERVED", "/output/nextCursor", index)


def _case_predecessors(cases: list[Any], violations: list[dict[str, Any]]) -> None:
    by_invocation = {
        document.get("invocationId"): document
        for document in cases
        if isinstance(document, dict) and isinstance(document.get("invocationId"), str)
    }
    for index, document in enumerate(cases, 1):
        if not isinstance(document, dict) or not isinstance(document.get("input"), dict):
            continue
        current_input = document["input"]
        previous_id = current_input.get("previousInvocationId")
        if previous_id is None:
            continue
        prior = by_invocation.get(previous_id)
        if prior is None or not isinstance(prior.get("output"), dict) or not isinstance(prior.get("input"), dict):
            _add(violations, "PAGE_PREDECESSOR_MISSING", "/input/previousInvocationId", index)
            continue
        if prior.get("operation") != document.get("operation"):
            _add(violations, "PAGE_PREDECESSOR_OPERATION_MISMATCH", "/operation", index)
        if prior["output"].get("continuation") != "next-page" or prior["output"].get("nextCursor") != current_input.get(
            "cursor"
        ):
            _add(violations, "PAGE_PREDECESSOR_CURSOR_MISMATCH", "/input/cursor", index)
        for field, code in (
            ("query", "PAGE_PREDECESSOR_QUERY_MISMATCH"),
            ("pageSize", "PAGE_PREDECESSOR_PAGE_SIZE_MISMATCH"),
        ):
            if prior["input"].get(field) != current_input.get(field):
                _add(violations, code, _pointer("input", field), index)


def _has_linked_search_continuation(cases: list[Any], valid_shapes: list[bool]) -> bool:
    search_by_invocation: dict[str, list[int]] = {}
    for index, (document, valid) in enumerate(zip(cases, valid_shapes, strict=True)):
        if valid and document["operation"] == "search" and isinstance(document["invocationId"], str):
            search_by_invocation.setdefault(document["invocationId"], []).append(index)
    for index, (document, valid) in enumerate(zip(cases, valid_shapes, strict=True)):
        if not valid or document["operation"] != "search" or not isinstance(document["input"], dict):
            continue
        current_input = document["input"]
        previous_id = current_input.get("previousInvocationId")
        cursor = current_input.get("cursor")
        if not isinstance(previous_id, str) or not isinstance(cursor, str) or not cursor:
            continue
        prior_indexes = search_by_invocation.get(previous_id, [])
        if len(prior_indexes) != 1 or prior_indexes[0] == index:
            continue
        prior = cases[prior_indexes[0]]
        prior_input, prior_output = prior["input"], prior["output"]
        if not isinstance(prior_input, dict) or not isinstance(prior_output, dict):
            continue
        if "cursor" in prior_input or "previousInvocationId" in prior_input:
            continue
        if prior_output.get("continuation") != "next-page" or prior_output.get("nextCursor") != cursor:
            continue
        if any(prior_input.get(field) != current_input.get(field) for field in ("query", "pageSize")):
            continue
        return True
    return False


def _case_coverage(
    manifest: PluginManifest | None, cases: list[Any], valid_shapes: list[bool], violations: list[dict[str, Any]]
) -> None:
    if manifest is None:
        return
    covered = {
        document["operation"]
        for document, valid in zip(cases, valid_shapes, strict=True)
        if valid and isinstance(document["operation"], str)
    }
    for index, operation in enumerate(manifest.operations):
        if operation not in covered:
            _add(violations, "CASE_OPERATION_COVERAGE_MISSING", _pointer("manifest", "operations", index))
        if operation == "search" and not _has_linked_search_continuation(cases, valid_shapes):
            _add(violations, "SEARCH_CONTINUATION_COVERAGE_MISSING", _pointer("manifest", "operations", index))


def validate(
    manifest_path: Path | None,
    package_path: Path | None,
    key_id: str | None,
    key_file: Path | None,
    case_paths: list[Path],
) -> dict[str, Any]:
    violations: list[dict[str, Any]] = []
    manifest = (
        _draft_manifest(manifest_path, violations)
        if manifest_path is not None
        else _signed_package(package_path, key_id or "", key_file, violations)  # type: ignore[arg-type]
    )
    inspection_valid = manifest is not None and not violations
    cases: list[Any] = []
    valid_shapes: list[bool] = []
    for index, path in enumerate(case_paths, 1):
        try:
            document = _read_json(path)
        except _InvalidJson:
            _add(violations, "CASE_JSON_INVALID", "", index)
            cases.append(None)
            valid_shapes.append(False)
            continue
        cases.append(document)
        valid = _case_shape(document, index, violations)
        valid_shapes.append(valid)
        if valid:
            _case_local(document, index, manifest, violations)
    _case_predecessors(cases, violations)
    _case_coverage(manifest, cases, valid_shapes, violations)
    violations.sort(key=lambda item: (item.get("case", 0), item["pointer"], item["code"]))
    return {
        "schemaVersion": "1.0",
        "result": "incomplete" if not case_paths and inspection_valid else "fail" if violations else "pass",
        "caseCount": len(case_paths),
        "violations": violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--manifest", type=Path, help="Unsigned local draft and declared files; never executed")
    source.add_argument("--package", type=Path, help="Signed connector archive; never executed")
    parser.add_argument("--publisher-key-id", help="Explicit trusted publisher key ID for --package")
    parser.add_argument("--publisher-key-file", type=Path, help="Raw 32-byte Ed25519 public key for --package")
    parser.add_argument("--case", action="append", type=Path, default=[], help="Synthetic conformance case JSON")
    arguments = parser.parse_args()
    if arguments.package is not None and (not arguments.publisher_key_id or arguments.publisher_key_file is None):
        parser.error("--package requires --publisher-key-id and --publisher-key-file")
    if arguments.manifest is not None and (arguments.publisher_key_id or arguments.publisher_key_file):
        parser.error("publisher key options require --package")
    report = validate(
        arguments.manifest,
        arguments.package,
        arguments.publisher_key_id,
        arguments.publisher_key_file,
        arguments.case,
    )
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
