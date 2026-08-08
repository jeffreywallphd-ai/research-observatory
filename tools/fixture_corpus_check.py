#!/usr/bin/env python3
"""Validate the licensed, deterministic, offline scholarly fixture corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

CORPUS_PATH = Path("tests/fixtures/scholarly-corpus")
MANIFEST_NAME = "manifest.json"
SCHEMA_NAME = "manifest.schema.json"
EXCLUDED_FILES = {MANIFEST_NAME, SCHEMA_NAME}
MEDIA_TYPE_BY_SUFFIX = {
    ".bib": "application/x-bibtex",
    ".json": "application/json",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".ris": "application/x-research-info-systems",
    ".txt": "text/plain",
    ".xml": "application/xml",
}
FEATURE_MEDIA_TYPES = {
    "metadata-json": {"application/json"},
    "metadata-ris": {"application/x-research-info-systems"},
    "metadata-bibtex": {"application/x-bibtex"},
    "structured-full-text": {"application/xml"},
    "plain-full-text": {"text/plain"},
    "pdf": {"application/pdf"},
    "malformed-json": {"application/json"},
    "malformed-xml": {"application/xml"},
    "malformed-pdf": {"application/pdf"},
    "table": {"application/xml", "application/pdf", "text/plain"},
    "citations": {"application/xml", "application/pdf", "text/plain"},
    "bibliography": {"application/xml", "application/pdf", "text/plain"},
}
FEATURE_OUTCOMES = {
    "pdf": "accept",
    "malformed-json": "reject",
    "malformed-xml": "reject",
    "malformed-pdf": "reject",
}
REQUIRED_FEATURES = {
    "metadata-json",
    "metadata-ris",
    "metadata-bibtex",
    "metadata-complete",
    "metadata-variant",
    "duplicate-identifier",
    "missing-fields",
    "unicode",
    "structured-full-text",
    "table",
    "citations",
    "bibliography",
    "pdf",
    "malformed-json",
    "malformed-xml",
    "malformed-pdf",
    "license-provenance",
}


def load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot load {label} {path}: {exc}") from exc


def schema_errors(manifest: Any, schema: Any) -> list[str]:
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        return [f"Invalid fixture manifest schema: {exc.message}"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(manifest), key=lambda error: [str(part) for part in error.path])
    return [f"manifest.{'.'.join(str(part) for part in error.path) or '<root>'}: {error.message}" for error in errors]


def safe_item_path(corpus: Path, raw_path: Any) -> tuple[Path | None, str | None]:
    if not isinstance(raw_path, str):
        return None, "fixture path must be a string"
    pure = PurePosixPath(raw_path)
    if pure.is_absolute() or ".." in pure.parts or "\\" in raw_path:
        return None, f"unsafe fixture path {raw_path!r}"
    lexical = corpus.joinpath(*pure.parts)
    try:
        resolved = lexical.resolve(strict=True)
        resolved.relative_to(corpus)
    except OSError, ValueError:
        return None, f"fixture path does not resolve inside the corpus: {raw_path}"
    if resolved != lexical:
        return None, f"fixture path must not be a symbolic link or redirect: {raw_path}"
    if not resolved.is_file():
        return None, f"fixture path is not a file: {raw_path}"
    return resolved, None


def pdf_failure_modes(payload: bytes) -> set[str]:
    modes: set[str] = set()
    if not payload.startswith(b"%PDF-1.") or not payload.rstrip().endswith(b"%%EOF"):
        modes.add("truncated-pdf")
    startxref = re.search(rb"startxref\s+(\d+)\s+%%EOF\s*$", payload)
    if startxref is None:
        modes.add("invalid-pdf-xref")
        return modes
    xref_offset = int(startxref.group(1))
    if xref_offset >= len(payload) or not payload[xref_offset:].startswith(b"xref\n"):
        modes.add("invalid-pdf-xref")
    object_offsets = {int(match.group(1)): match.start() for match in re.finditer(rb"(?m)^(\d+) 0 obj\s*$", payload)}
    xref_region = payload[xref_offset:]
    header = re.match(rb"xref\r?\n0 (\d+)\r?\n", xref_region)
    if header is None:
        modes.add("invalid-pdf-xref")
        return modes
    declared_count = int(header.group(1))
    cursor = header.end()
    entries: list[tuple[int, int, bytes]] = []
    for _ in range(declared_count):
        entry = re.match(rb"(\d{10}) (\d{5}) ([fn]) \r?\n", xref_region[cursor:])
        if entry is None:
            modes.add("invalid-pdf-xref")
            return modes
        entries.append((int(entry.group(1)), int(entry.group(2)), entry.group(3)))
        cursor += entry.end()
    if not xref_region[cursor:].startswith(b"trailer"):
        modes.add("invalid-pdf-xref")
    trailer_size = re.search(rb"trailer\s*<<[^>]*?/Size\s+(\d+)", xref_region[cursor:])
    if trailer_size is None or int(trailer_size.group(1)) != declared_count:
        modes.add("invalid-pdf-xref")
    if not entries or entries[0] != (0, 65535, b"f"):
        modes.add("invalid-pdf-xref")
    expected_objects = set(range(1, declared_count))
    if set(object_offsets) != expected_objects:
        modes.add("invalid-pdf-xref")
    for object_number in expected_objects:
        if object_number >= len(entries):
            modes.add("invalid-pdf-xref")
            continue
        offset, generation, state = entries[object_number]
        if offset != object_offsets.get(object_number) or generation != 0 or state != b"n":
            modes.add("invalid-pdf-xref")
    return modes


def content_failure_modes(payload: bytes, media_type: str) -> set[str]:
    if media_type == "application/json":
        try:
            json.loads(payload.decode("utf-8"))
        except UnicodeError, json.JSONDecodeError:
            return {"invalid-json"}
        return set()
    if media_type == "application/xml":
        try:
            ET.fromstring(payload)
        except UnicodeError, ET.ParseError:
            return {"invalid-xml"}
        return set()
    if media_type == "application/pdf":
        return pdf_failure_modes(payload)
    try:
        text = payload.decode("utf-8")
    except UnicodeError:
        return {"invalid-utf8"}
    if media_type == "application/x-research-info-systems":
        if text.count("TY  - ") < 1 or text.count("TY  - ") != text.count("ER  -"):
            return {"invalid-ris"}
    elif media_type == "application/x-bibtex" and ("@" not in text or text.count("{") != text.count("}")):
        return {"invalid-bibtex"}
    return set()


def semantic_feature_errors(item: dict[str, Any], payload: bytes) -> list[str]:
    item_id = str(item.get("id", "<unknown>"))
    media_type = str(item.get("mediaType", ""))
    expected = item.get("expectedOutcome")
    features = set(item.get("features", []))
    errors: list[str] = []

    for feature in sorted(features):
        allowed_media = FEATURE_MEDIA_TYPES.get(feature)
        if allowed_media is not None and media_type not in allowed_media:
            errors.append(f"{item_id}: feature {feature!r} is incompatible with {media_type!r}")
        required_outcome = FEATURE_OUTCOMES.get(feature)
        if required_outcome is not None and expected != required_outcome:
            errors.append(f"{item_id}: feature {feature!r} requires outcome {required_outcome!r}")

    if expected != "accept":
        return errors

    xml_root: ET.Element | None = None
    if media_type == "application/xml":
        try:
            xml_root = ET.fromstring(payload)
        except ET.ParseError:
            return errors
        searchable = " ".join(xml_root.itertext())
    elif media_type == "application/pdf":
        searchable = payload.decode("latin-1")
    else:
        try:
            searchable = payload.decode("utf-8")
        except UnicodeError:
            return errors

    if "structured-full-text" in features and (
        xml_root is None or xml_root.tag != "article" or xml_root.find(".//body") is None
    ):
        errors.append(f"{item_id}: structured-full-text lacks an article body")
    if "plain-full-text" in features and not re.search(r"(?ms)^ABSTRACT\s*$.*^METHODS\s*$", searchable):
        errors.append(f"{item_id}: plain-full-text lacks expected scholarly sections")
    if "table" in features:
        has_table = xml_root is not None and xml_root.find(".//table") is not None
        has_table = has_table or re.search(r"(?i)\btable\s+\d+\b", searchable) is not None
        if not has_table:
            errors.append(f"{item_id}: table is declared but no table structure or marker exists")
    if "citations" in features:
        has_citations = xml_root is not None and bool(xml_root.findall(".//xref[@ref-type='bibr']"))
        has_citations = has_citations or re.search(r"\[\d+\]", searchable) is not None
        has_citations = has_citations or len(re.findall(r"\b[A-Z][A-Za-z]+\s+20\d{2}\b", searchable)) >= 2
        if not has_citations:
            errors.append(f"{item_id}: citations are declared but no citation markers exist")
    if "bibliography" in features:
        has_bibliography = xml_root is not None and xml_root.find(".//ref-list") is not None
        has_bibliography = has_bibliography or re.search(r"(?i)\breferences\b", searchable) is not None
        if not has_bibliography:
            errors.append(f"{item_id}: bibliography is declared but no reference section exists")
    if "metadata-ris" in features:
        records = [record for record in searchable.split("ER  -") if "TY  -" in record]
        if len(records) < 2 or not any("AU  -" not in record or "PY  -" not in record for record in records):
            errors.append(f"{item_id}: RIS metadata lacks variant records with missing fields")
    if "metadata-bibtex" in features:
        entries = [entry for entry in re.split(r"(?m)(?=^@\w+\{)", searchable) if entry.lstrip().startswith("@")]
        if len(entries) < 2 or not any(re.search(r"(?im)^\s*author\s*=", entry) is None for entry in entries):
            errors.append(f"{item_id}: BibTeX metadata lacks variant entries with missing fields")
    return errors


def feature_errors(corpus: Path, manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    items = manifest.get("items", [])
    features = {feature for item in items for feature in item.get("features", [])}
    missing = sorted(REQUIRED_FEATURES - features)
    if missing:
        errors.append(f"fixture feature coverage is incomplete: {', '.join(missing)}")

    metadata_path = corpus / "metadata/records.json"
    try:
        records = json.loads(metadata_path.read_text(encoding="utf-8"))["records"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        return [*errors, f"cannot inspect metadata edge cases: {exc}"]
    required_complete = {"title", "authors", "issued", "containerTitle", "doi", "abstract"}
    has_complete_metadata = any(
        required_complete <= set(record) and all(record.get(field) for field in required_complete) for record in records
    )
    if not has_complete_metadata:
        errors.append("metadata-complete is declared but no complete record exists")
    doi_counts = Counter(str(record.get("doi", "")).casefold() for record in records if record.get("doi"))
    if not any(count > 1 for count in doi_counts.values()):
        errors.append("duplicate-identifier is declared but no case-insensitive duplicate DOI exists")
    has_missing_fields = any(
        not record.get("authors") or not record.get("issued") or not record.get("abstract") for record in records
    )
    if not has_missing_fields:
        errors.append("missing-fields is declared but every metadata record is complete")
    has_unicode = any(
        any(ord(character) > 127 for character in json.dumps(record, ensure_ascii=False)) for record in records
    )
    if not has_unicode:
        errors.append("unicode is declared but no non-ASCII metadata exists")

    try:
        article = ET.parse(corpus / "fulltext/article.xml").getroot()
    except (OSError, ET.ParseError) as exc:
        return [*errors, f"cannot inspect structured full text: {exc}"]
    if article.find(".//table") is None:
        errors.append("table is declared but structured full text has no table")
    if not article.findall(".//xref[@ref-type='bibr']") or article.find(".//ref-list") is None:
        errors.append("citations/bibliography are declared but structured links are absent")
    return errors


def corpus_errors(corpus: Path) -> list[str]:
    try:
        corpus = corpus.resolve(strict=True)
    except OSError as exc:
        return [f"Cannot resolve fixture corpus {corpus}: {exc}"]
    manifest_path, manifest_path_error = safe_item_path(corpus, MANIFEST_NAME)
    schema_path, schema_path_error = safe_item_path(corpus, SCHEMA_NAME)
    control_errors = [
        f"fixture control file: {error}" for error in (manifest_path_error, schema_path_error) if error is not None
    ]
    if control_errors:
        return control_errors
    assert manifest_path is not None and schema_path is not None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"Cannot load fixture corpus contract: {exc}"]
    errors = schema_errors(manifest, schema)
    if errors or not isinstance(manifest, dict):
        return errors

    items = manifest.get("items", [])
    ids = [item.get("id") for item in items]
    paths = [item.get("path") for item in items]
    if len(ids) != len(set(ids)):
        errors.append("fixture item IDs must be unique")
    if len(paths) != len(set(paths)):
        errors.append("fixture item paths must be unique")

    declared_paths: set[str] = set()
    for item in items:
        raw_path = item.get("path")
        path, path_error = safe_item_path(corpus, raw_path)
        if path_error:
            errors.append(f"{item.get('id', '<unknown>')}: {path_error}")
            continue
        assert path is not None and isinstance(raw_path, str)
        declared_paths.add(raw_path)
        try:
            payload = path.read_bytes()
        except OSError as exc:
            errors.append(f"{item['id']}: cannot read {raw_path}: {exc}")
            continue
        actual_hash = hashlib.sha256(payload).hexdigest()
        if actual_hash != item.get("sha256"):
            errors.append(f"{item['id']}: SHA-256 mismatch for {raw_path}")
        if len(payload) != item.get("bytes"):
            errors.append(f"{item['id']}: byte count mismatch for {raw_path}")
        media_type = item.get("mediaType", "")
        expected_media_type = MEDIA_TYPE_BY_SUFFIX.get(path.suffix.casefold())
        if expected_media_type is None:
            errors.append(f"{item['id']}: unsupported fixture extension {path.suffix!r}")
        elif media_type != expected_media_type:
            errors.append(f"{item['id']}: mediaType {media_type!r} does not match path type {expected_media_type!r}")
        failure_modes = content_failure_modes(payload, media_type)
        expected = item.get("expectedOutcome")
        failure_mode = item.get("failureMode")
        if expected == "accept" and failure_modes:
            errors.append(f"{item['id']}: accepted fixture fails validation: {sorted(failure_modes)}")
        elif expected == "accept" and failure_mode is not None:
            errors.append(f"{item['id']}: accepted fixture must have null failureMode")
        elif expected == "reject" and not failure_modes:
            errors.append(f"{item['id']}: rejection fixture unexpectedly passes structural validation")
        elif expected == "reject" and failure_mode not in failure_modes:
            errors.append(f"{item['id']}: expected failureMode {failure_mode!r}; observed {sorted(failure_modes)}")
        errors.extend(semantic_feature_errors(item, payload))

    actual_paths = {
        path.relative_to(corpus).as_posix()
        for path in corpus.rglob("*")
        if path.is_file() and path.relative_to(corpus).as_posix() not in EXCLUDED_FILES
    }
    if declared_paths != actual_paths:
        for inventory_path in sorted(actual_paths - declared_paths):
            errors.append(f"undocumented fixture file: {inventory_path}")
        for inventory_path in sorted(declared_paths - actual_paths):
            errors.append(f"manifest references missing fixture file: {inventory_path}")
    errors.extend(feature_errors(corpus, manifest))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="repository root")
    args = parser.parse_args()
    root = Path(args.repo).resolve()
    corpus = (root / CORPUS_PATH).resolve(strict=False)
    try:
        corpus.relative_to(root)
    except ValueError:
        print(f"Fixture corpus escapes repository: {corpus}")
        return 1
    errors = corpus_errors(corpus)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    manifest = load_json(corpus / MANIFEST_NAME, "fixture manifest")
    features = {feature for item in manifest["items"] for feature in item["features"]}
    rejected = sum(item["expectedOutcome"] == "reject" for item in manifest["items"])
    print(
        f"Fixture corpus: PASS - {len(manifest['items'])} files, {len(features)} features, "
        f"{rejected} intentional rejection cases, CC0-1.0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
