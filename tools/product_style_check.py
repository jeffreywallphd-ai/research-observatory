#!/usr/bin/env python3
"""Fail-closed production-style reuse and maintainability analysis.

The governed reference remains the visual authority.  This checker evaluates the
small production CSS boundary that implements it and intentionally does not
inspect or rewrite the approved reference package.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
import zlib
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from build_manifest import path_identity, windows_path_locks
from ui_conformance import confined_path, stable_file_bytes

TOKEN_PATH = "design/ui-reference/assets/tokens.css"
STYLE_PATHS = (
    "packages/ui-components/src/styles.css",
    "apps/desktop/src/app.css",
)
EXCEPTION_PATH = "verification/product-style-exceptions.json"
RENDERER_ROOTS = (
    "packages/ui-components/src",
    "apps/desktop/src",
)

MAX_CLASS_SPECIFICITY = 2
MAX_TYPE_SPECIFICITY = 4
MAX_EXCEPTIONS = 16
MATERIAL_DECLARATION_COUNT = 3

EXCEPTIONABLE_CODES = frozenset(
    {
        "duplicate-declaration-group",
        "raw-geometry",
        "selector-specificity",
    }
)
EXCEPTION_RECORD_KEYS = frozenset({"schemaVersion", "documentType", "authority", "reviewBoundary", "exceptions"})
EXCEPTION_ENTRY_KEYS = frozenset({"id", "kind", "signature", "scope", "rationale"})
EXPECTED_EXCEPTION_HEADER = {
    "schemaVersion": "1.0",
    "documentType": "product-style-analysis-exceptions",
    "authority": "ECR-0007/W1.A08.T01",
    "reviewBoundary": "independent-commit-bound-task-review",
}

PHYSICAL_PROPERTIES = re.compile(
    r"^(?:top|right|bottom|left|"
    r"(?:margin|padding|border)-(?:top|right|bottom|left)(?:-[a-z-]+)?|"
    r"border-(?:top|right|bottom|left)-radius)$"
)
PHYSICAL_TEXT_ALIGN = frozenset({"left", "right"})
RAW_LENGTH = re.compile(
    r"(?<![a-zA-Z0-9_-])-?(?:\d+(?:\.\d+)?|\.\d+)"
    r"(?:px|rem|em|ch|ex|cap|ic|lh|rlh|vw|vh|vmin|vmax|cm|mm|in|pt|pc|q)\b",
    re.IGNORECASE,
)
SPACING_PROPERTIES = re.compile(r"^(?:gap|row-gap|column-gap|margin(?:-[a-z-]+)?|padding(?:-[a-z-]+)?|border-radius)$")
DIMENSION_PROPERTIES = frozenset(
    {
        "width",
        "min-width",
        "max-width",
        "height",
        "min-height",
        "max-height",
        "inline-size",
        "min-inline-size",
        "max-inline-size",
        "block-size",
        "min-block-size",
        "max-block-size",
    }
)
SEMANTIC_DIMENSION_SELECTOR = re.compile(
    r"(?:\.ro-|button\b|input\b|select\b|textarea\b|dialog\b|card\b|panel\b|table\b|notice\b|"
    r"form\b|control\b|confirmation\b|locked\b|visually-hidden\b)",
    re.IGNORECASE,
)
CUSTOM_PROPERTY_REFERENCE = re.compile(r"var\(\s*(--[a-zA-Z0-9_-]+)")
INLINE_STYLE_PATTERNS = (
    ("inline style attribute", re.compile(r"\bstyle\s*=", re.IGNORECASE)),
    ("CSS-in-JS css prop", re.compile(r"\bcss\s*=", re.IGNORECASE)),
    ("CSS-in-JS styled factory", re.compile(r"\bstyled(?:\s*\(|\.[a-zA-Z])")),
    ("CSS-in-JS tagged template", re.compile(r"\bcss\s*`")),
    ("embedded style element", re.compile(r"<style\b", re.IGNORECASE)),
    ("HTML style injection", re.compile(r"\bdangerouslySetInnerHTML\b")),
)


@dataclass(frozen=True)
class Declaration:
    property: str
    value: str
    line: int


@dataclass(frozen=True)
class Rule:
    path: str
    selector: str
    context: str
    declarations: tuple[Declaration, ...]
    line: int


def _normalize_space(value: str) -> str:
    value = re.sub(r"\s+", " ", value.strip())
    value = re.sub(r"\s*,\s*", ", ", value)
    return re.sub(r"\s*([>+~])\s*", r" \1 ", value).strip()


def _split_top_level(value: str, delimiter: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escaped = False
    for index, character in enumerate(value):
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            quote = character
        elif character in "([":
            depth += 1
        elif character in ")]":
            depth = max(0, depth - 1)
        elif character == delimiter and depth == 0:
            parts.append(value[start:index])
            start = index + 1
    parts.append(value[start:])
    return parts


def _normalize_selector(selector: str) -> str:
    members = (_normalize_space(member) for member in _split_top_level(selector, ","))
    return ", ".join(sorted(member for member in members if member))


def _strip_comments(source: str) -> str:
    def blank(match: re.Match[str]) -> str:
        return "".join("\n" if character == "\n" else " " for character in match.group())

    return re.sub(r"/\*.*?\*/", blank, source, flags=re.DOTALL)


def _matching_delimiter(source: str, opening: int, opening_character: str, closing_character: str) -> int:
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(opening, len(source)):
        character = source[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            quote = character
        elif character == opening_character:
            depth += 1
        elif character == closing_character:
            depth -= 1
            if depth == 0:
                return index
    raise ValueError(f"unclosed {opening_character!r} at character {opening}")


def _find_open_brace(source: str, start: int) -> int | None:
    quote: str | None = None
    escaped = False
    for index in range(start, len(source)):
        character = source[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            quote = character
        elif character == "{":
            return index
    return None


def _parse_declarations(body: str, base_line: int) -> tuple[Declaration, ...]:
    declarations: list[Declaration] = []
    offset = 0
    for segment in _split_top_level(body, ";"):
        stripped = segment.strip()
        if not stripped:
            offset += len(segment) + 1
            continue
        if ":" not in stripped:
            raise ValueError(f"declaration has no colon near line {base_line + body[:offset].count(chr(10))}")
        property_name, value = stripped.split(":", 1)
        property_name = property_name.strip().lower()
        if re.fullmatch(r"(?:--)?[a-zA-Z_][a-zA-Z0-9_-]*", property_name) is None:
            raise ValueError(f"invalid property {property_name!r} near line {base_line + body[:offset].count(chr(10))}")
        declarations.append(
            Declaration(
                property=property_name,
                value=_normalize_space(value),
                line=base_line + body[:offset].count("\n"),
            )
        )
        offset += len(segment) + 1
    return tuple(declarations)


def _parse_rules(
    source: str,
    path: str,
    *,
    context: tuple[str, ...] = (),
    base_offset: int = 0,
) -> list[Rule]:
    source = _strip_comments(source)
    rules: list[Rule] = []
    cursor = 0
    while True:
        opening = _find_open_brace(source, cursor)
        if opening is None:
            trailing = source[cursor:].strip()
            if trailing and not trailing.startswith("@"):
                raise ValueError(f"unexpected trailing CSS in {path}: {trailing[:40]!r}")
            break
        prelude = source[cursor:opening].strip()
        if ";" in prelude:
            prelude = prelude.rsplit(";", 1)[1].strip()
        closing = _matching_delimiter(source, opening, "{", "}")
        body = source[opening + 1 : closing]
        absolute_opening = base_offset + opening
        line = source[:opening].count("\n") + 1
        normalized_prelude = _normalize_space(prelude)
        if not normalized_prelude:
            raise ValueError(f"empty CSS rule in {path} near line {line}")
        if normalized_prelude.startswith("@"):
            at_name = normalized_prelude.split(None, 1)[0].lower()
            if at_name in {"@media", "@supports", "@container", "@layer"}:
                rules.extend(
                    _parse_rules(
                        body,
                        path,
                        context=(*context, normalized_prelude),
                        base_offset=absolute_opening + 1,
                    )
                )
        else:
            rules.append(
                Rule(
                    path=path,
                    selector=_normalize_selector(normalized_prelude),
                    context=" > ".join(context),
                    declarations=_parse_declarations(body, line),
                    line=line,
                )
            )
        cursor = closing + 1
    return rules


def _selector_specificity(selector: str) -> tuple[int, int, int]:
    ids = classes = types = 0
    cursor = 0
    expects_type = True

    def identifier_end(start: int) -> int:
        match = re.match(r"[a-zA-Z_][a-zA-Z0-9_-]*", selector[start:])
        return start + len(match.group()) if match else start

    while cursor < len(selector):
        character = selector[cursor]
        if character.isspace() or character in ">+~":
            expects_type = True
            cursor += 1
            continue
        if character == "#":
            ids += 1
            cursor = max(cursor + 1, identifier_end(cursor + 1))
            expects_type = False
            continue
        if character == ".":
            classes += 1
            cursor = max(cursor + 1, identifier_end(cursor + 1))
            expects_type = False
            continue
        if character == "[":
            classes += 1
            cursor = _matching_delimiter(selector, cursor, "[", "]") + 1
            expects_type = False
            continue
        if character == ":":
            pseudo_element = cursor + 1 < len(selector) and selector[cursor + 1] == ":"
            name_start = cursor + (2 if pseudo_element else 1)
            name_end = identifier_end(name_start)
            name = selector[name_start:name_end].lower()
            if pseudo_element:
                types += 1
            cursor = name_end
            if cursor < len(selector) and selector[cursor] == "(":
                closing = _matching_delimiter(selector, cursor, "(", ")")
                arguments = selector[cursor + 1 : closing]
                if not pseudo_element and name in {"is", "not", "has"}:
                    alternatives = [_selector_specificity(item) for item in _split_top_level(arguments, ",")]
                    nested = max(alternatives, default=(0, 0, 0))
                    ids += nested[0]
                    classes += nested[1]
                    types += nested[2]
                elif not pseudo_element and name != "where":
                    classes += 1
                    if name in {"nth-child", "nth-last-child"} and " of " in arguments:
                        selector_arguments = arguments.split(" of ", 1)[1]
                        alternatives = [
                            _selector_specificity(item) for item in _split_top_level(selector_arguments, ",")
                        ]
                        nested = max(alternatives, default=(0, 0, 0))
                        ids += nested[0]
                        classes += nested[1]
                        types += nested[2]
                cursor = closing + 1
            elif not pseudo_element:
                classes += 1
            expects_type = False
            continue
        if character == "*":
            expects_type = False
            cursor += 1
            continue
        if character.isalpha() or character == "_":
            end = identifier_end(cursor)
            if expects_type:
                types += 1
            cursor = max(cursor + 1, end)
            expects_type = False
            continue
        cursor += 1
    return ids, classes, types


def _issue(code: str, signature: str, message: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "signature": signature, "message": message, **details}


def _exception_record_errors(record: Any) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    valid: dict[str, dict[str, Any]] = {}
    if not isinstance(record, dict):
        return [
            _issue(
                "exception-record",
                "exception-record|root",
                "product style exception record must be a JSON object",
            )
        ], valid
    if set(record) != EXCEPTION_RECORD_KEYS:
        issues.append(
            _issue(
                "exception-record",
                "exception-record|keys",
                "product style exception record fields must be exact",
            )
        )
    for field, expected in EXPECTED_EXCEPTION_HEADER.items():
        if record.get(field) != expected:
            issues.append(
                _issue(
                    "exception-record",
                    f"exception-record|{field}",
                    f"product style exception record {field} must equal {expected!r}",
                )
            )
    entries = record.get("exceptions")
    if not isinstance(entries, list):
        issues.append(
            _issue(
                "exception-record",
                "exception-record|exceptions",
                "product style exceptions must be an array",
            )
        )
        return issues, valid
    if len(entries) > MAX_EXCEPTIONS:
        issues.append(
            _issue(
                "exception-record",
                "exception-record|size",
                f"product style exception record exceeds the reviewed maximum of {MAX_EXCEPTIONS}",
            )
        )
    seen_ids: set[str] = set()
    for index, entry in enumerate(entries):
        prefix = f"exception-record|entry-{index}"
        if not isinstance(entry, dict) or set(entry) != EXCEPTION_ENTRY_KEYS:
            issues.append(_issue("exception-record", prefix, f"style exception entry {index} fields must be exact"))
            continue
        identifier = entry.get("id")
        kind = entry.get("kind")
        signature = entry.get("signature")
        scope = entry.get("scope")
        rationale = entry.get("rationale")
        valid_entry = True
        if not isinstance(identifier, str) or re.fullmatch(r"W1-A08-T01-C\d{2}", identifier) is None:
            issues.append(_issue("exception-record", prefix, f"style exception entry {index} has an invalid id"))
            valid_entry = False
        elif identifier in seen_ids:
            issues.append(_issue("exception-record", prefix, f"style exception id {identifier} is duplicated"))
            valid_entry = False
        else:
            seen_ids.add(identifier)
        if kind not in EXCEPTIONABLE_CODES:
            issues.append(_issue("exception-record", prefix, f"style exception {identifier!r} has an invalid kind"))
            valid_entry = False
        if not isinstance(signature, str) or not signature.startswith(f"{kind}|"):
            issues.append(
                _issue(
                    "exception-record",
                    prefix,
                    f"style exception {identifier!r} has an invalid signature",
                )
            )
            valid_entry = False
        elif "*" in signature or "?" in signature:
            issues.append(
                _issue(
                    "exception-record",
                    prefix,
                    f"style exception {identifier!r} must not contain wildcard characters",
                )
            )
            valid_entry = False
        if scope not in {"composition", "accessibility"}:
            issues.append(_issue("exception-record", prefix, f"style exception {identifier!r} has an invalid scope"))
            valid_entry = False
        if not isinstance(rationale, str) or len(rationale.strip()) < 40:
            issues.append(
                _issue(
                    "exception-record",
                    prefix,
                    f"style exception {identifier!r} needs a detailed rationale",
                )
            )
            valid_entry = False
        if isinstance(signature, str) and signature in valid:
            issues.append(_issue("exception-record", prefix, f"style exception signature {signature!r} is duplicated"))
            valid_entry = False
        if valid_entry and isinstance(signature, str):
            valid[signature] = entry
    return issues, valid


def load_product_style_sources(
    repo: Path,
) -> tuple[str, dict[str, str], dict[str, str], Any]:
    token_source = (repo / TOKEN_PATH).read_text(encoding="utf-8")
    css_paths = {path.relative_to(repo).as_posix() for root in RENDERER_ROOTS for path in (repo / root).rglob("*.css")}
    missing_styles = set(STYLE_PATHS) - css_paths
    if missing_styles:
        raise OSError(f"required production styles are missing: {', '.join(sorted(missing_styles))}")
    css_sources = {path: (repo / path).read_text(encoding="utf-8") for path in sorted(css_paths)}
    renderer_sources: dict[str, str] = {}
    for root in RENDERER_ROOTS:
        for path in sorted((repo / root).rglob("*.tsx")):
            if path.name.endswith(".test.tsx"):
                continue
            relative = path.relative_to(repo).as_posix()
            renderer_sources[relative] = path.read_text(encoding="utf-8")
    exception_record = json.loads((repo / EXCEPTION_PATH).read_text(encoding="utf-8"))
    return token_source, css_sources, renderer_sources, exception_record


def analyze_product_style_sources(
    token_source: str,
    css_sources: dict[str, str],
    renderer_sources: dict[str, str],
    exception_record: Any,
) -> dict[str, Any]:
    issues, valid_exceptions = _exception_record_errors(exception_record)
    rules: list[Rule] = []
    token_rules: list[Rule] = []
    try:
        token_rules = _parse_rules(token_source, TOKEN_PATH)
    except ValueError as exc:
        issues.append(_issue("css-parse", f"css-parse|{TOKEN_PATH}", f"cannot parse {TOKEN_PATH}: {exc}"))
    for path, source in sorted(css_sources.items()):
        try:
            rules.extend(_parse_rules(source, path))
        except ValueError as exc:
            issues.append(_issue("css-parse", f"css-parse|{path}", f"cannot parse {path}: {exc}"))

    all_rules = [*token_rules, *rules]
    canonical_properties = {
        declaration.property
        for rule in token_rules
        for declaration in rule.declarations
        if declaration.property.startswith("--")
    }
    defined_properties = {
        declaration.property
        for rule in all_rules
        for declaration in rule.declarations
        if declaration.property.startswith("--")
    }
    referenced_properties: set[str] = set()
    for rule in all_rules:
        for declaration in rule.declarations:
            referenced_properties.update(CUSTOM_PROPERTY_REFERENCE.findall(declaration.value))
    for property_name in sorted(referenced_properties - defined_properties):
        issues.append(
            _issue(
                "undefined-custom-property",
                f"undefined-custom-property|{property_name}",
                f"custom property {property_name} is referenced but never defined by the canonical token or "
                "production style boundary",
                property=property_name,
            )
        )

    for rule in rules:
        for declaration in rule.declarations:
            if not declaration.property.startswith("--"):
                continue
            if declaration.property in canonical_properties:
                signature = (
                    f"canonical-token-redefinition|{rule.path}|{rule.context or 'global'}|"
                    f"{rule.selector}|{declaration.property}"
                )
                issues.append(
                    _issue(
                        "canonical-token-redefinition",
                        signature,
                        f"{rule.path}:{declaration.line} redefines canonical token {declaration.property}",
                        path=rule.path,
                        selector=rule.selector,
                        property=declaration.property,
                    )
                )
            elif not declaration.property.startswith("--ro-"):
                signature = (
                    f"second-token-source|{rule.path}|{rule.context or 'global'}|{rule.selector}|{declaration.property}"
                )
                issues.append(
                    _issue(
                        "second-token-source",
                        signature,
                        f"{rule.path}:{declaration.line} defines non-canonical semantic token "
                        f"{declaration.property}; production-local composition properties must use the --ro- namespace",
                        path=rule.path,
                        selector=rule.selector,
                        property=declaration.property,
                    )
                )

    for rule in all_rules:
        custom_counts: dict[str, int] = {}
        for declaration in rule.declarations:
            if declaration.property.startswith("--"):
                custom_counts[declaration.property] = custom_counts.get(declaration.property, 0) + 1
        for property_name, count in sorted(custom_counts.items()):
            if count > 1:
                signature = f"duplicate-custom-property|{rule.path}|{rule.context}|{rule.selector}|{property_name}"
                issues.append(
                    _issue(
                        "duplicate-custom-property",
                        signature,
                        f"{rule.path}:{rule.line} defines {property_name} {count} times in {rule.selector}",
                        path=rule.path,
                        selector=rule.selector,
                        property=property_name,
                    )
                )

    material_groups: dict[tuple[str, tuple[tuple[str, str], ...]], list[Rule]] = {}
    for rule in rules:
        fingerprint = tuple(sorted((declaration.property, declaration.value) for declaration in rule.declarations))
        if len(fingerprint) >= 2:
            material_groups.setdefault((rule.context, fingerprint), []).append(rule)

    declaration_inventory: list[dict[str, Any]] = []
    for (context, fingerprint), grouped_rules in sorted(material_groups.items()):
        occurrences = sorted({f"{rule.path}::{rule.selector}" for rule in grouped_rules})
        paths = sorted({rule.path for rule in grouped_rules})
        digest = hashlib.sha256(
            json.dumps(fingerprint, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        declaration_inventory.append(
            {
                "paths": paths,
                "context": context or "global",
                "fingerprintSha256": digest,
                "declarationCount": len(fingerprint),
                "occurrences": occurrences,
            }
        )
        is_material_duplicate = (
            len(occurrences) >= 2 if len(fingerprint) >= MATERIAL_DECLARATION_COUNT else len(occurrences) >= 3
        )
        if is_material_duplicate:
            declaration_text = ";".join(f"{name}:{value}" for name, value in fingerprint)
            signature = f"duplicate-declaration-group|{context or 'global'}|{','.join(occurrences)}|{declaration_text}"
            issues.append(
                _issue(
                    "duplicate-declaration-group",
                    signature,
                    f"production CSS repeats one normalized {len(fingerprint)}-declaration group across "
                    f"{', '.join(occurrences)}",
                    paths=paths,
                    context=context or "global",
                    occurrences=occurrences,
                    declarations=[{"property": name, "value": value} for name, value in fingerprint],
                )
            )

    specificity_inventory: list[dict[str, Any]] = []
    for rule in rules:
        for selector in _split_top_level(rule.selector, ","):
            normalized_selector = _normalize_space(selector)
            specificity = _selector_specificity(normalized_selector)
            specificity_inventory.append(
                {
                    "path": rule.path,
                    "selector": normalized_selector,
                    "specificity": list(specificity),
                }
            )
            if specificity[0] > 0 or specificity[1] > MAX_CLASS_SPECIFICITY or specificity[2] > MAX_TYPE_SPECIFICITY:
                signature = (
                    f"selector-specificity|{rule.path}|{rule.context or 'global'}|"
                    f"{normalized_selector}|{specificity[0]},{specificity[1]},{specificity[2]}"
                )
                issues.append(
                    _issue(
                        "selector-specificity",
                        signature,
                        f"{rule.path}:{rule.line} selector {normalized_selector!r} has uncontrolled "
                        f"specificity {specificity}",
                        path=rule.path,
                        selector=normalized_selector,
                        specificity=list(specificity),
                    )
                )

    raw_geometry: list[dict[str, Any]] = []
    physical_direction: list[dict[str, Any]] = []
    for rule in rules:
        for declaration in rule.declarations:
            value_lower = declaration.value.lower()
            if PHYSICAL_PROPERTIES.fullmatch(declaration.property) or (
                declaration.property == "text-align" and value_lower in PHYSICAL_TEXT_ALIGN
            ):
                signature = (
                    f"physical-direction|{rule.path}|{rule.context or 'global'}|{rule.selector}|"
                    f"{declaration.property}|{declaration.value}"
                )
                entry = {
                    "path": rule.path,
                    "selector": rule.selector,
                    "property": declaration.property,
                    "value": declaration.value,
                }
                physical_direction.append({**entry, "signature": signature})
                issues.append(
                    _issue(
                        "physical-direction",
                        signature,
                        f"{rule.path}:{declaration.line} must express {declaration.property} with a logical "
                        "property/value",
                        **entry,
                    )
                )
            is_spacing = SPACING_PROPERTIES.fullmatch(declaration.property) is not None
            is_semantic_dimension = (
                declaration.property in DIMENSION_PROPERTIES
                and SEMANTIC_DIMENSION_SELECTOR.search(rule.selector) is not None
            )
            if (is_spacing or is_semantic_dimension) and RAW_LENGTH.search(declaration.value):
                signature = (
                    f"raw-geometry|{rule.path}|{rule.context or 'global'}|{rule.selector}|"
                    f"{declaration.property}|{declaration.value}"
                )
                raw_geometry.append(
                    {
                        "path": rule.path,
                        "context": rule.context or "global",
                        "selector": rule.selector,
                        "property": declaration.property,
                        "value": declaration.value,
                        "signature": signature,
                    }
                )
                issues.append(
                    _issue(
                        "raw-geometry",
                        signature,
                        f"{rule.path}:{declaration.line} has unexplained raw spacing/control/card geometry "
                        f"{declaration.property}: {declaration.value}",
                        path=rule.path,
                        selector=rule.selector,
                        property=declaration.property,
                        value=declaration.value,
                    )
                )

    for path, source in sorted(renderer_sources.items()):
        uncommented = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.DOTALL)
        for label, pattern in INLINE_STYLE_PATTERNS:
            match = pattern.search(uncommented)
            if match is None:
                continue
            line = uncommented[: match.start()].count("\n") + 1
            signature = f"renderer-style-escape|{path}|{label}|{line}"
            issues.append(
                _issue(
                    "renderer-style-escape",
                    signature,
                    f"{path}:{line} uses a forbidden {label}",
                    path=path,
                    escape=label,
                )
            )

    used_exceptions: set[str] = set()
    unsuppressed: list[dict[str, Any]] = []
    for issue in issues:
        exception = valid_exceptions.get(issue["signature"])
        if exception is not None and issue["code"] in EXCEPTIONABLE_CODES and exception["kind"] == issue["code"]:
            used_exceptions.add(issue["signature"])
            issue["exceptionId"] = exception["id"]
        else:
            unsuppressed.append(issue)
    for signature, exception in sorted(valid_exceptions.items()):
        if signature not in used_exceptions:
            unsuppressed.append(
                _issue(
                    "exception-record",
                    f"exception-record|unused|{exception['id']}",
                    f"style exception {exception['id']} is stale or does not exactly match a current violation",
                )
            )

    specificity_inventory.sort(key=lambda item: (item["specificity"], item["path"], item["selector"]), reverse=True)
    unsuppressed.sort(key=lambda issue: (issue["code"], issue["signature"]))
    raw_geometry.sort(key=lambda item: item["signature"])
    physical_direction.sort(key=lambda item: item["signature"])
    return {
        "ok": not unsuppressed,
        "errors": [f"[{issue['code']}] {issue['message']}" for issue in unsuppressed],
        "details": {
            "stylePaths": sorted(css_sources),
            "rendererFileCount": len(renderer_sources),
            "cssRuleCount": len(rules),
            "customPropertyDefinitionCount": len(defined_properties),
            "customPropertyReferenceCount": len(referenced_properties),
            "materialDeclarationGroups": declaration_inventory,
            "selectorSpecificity": {
                "maximum": specificity_inventory[0]["specificity"] if specificity_inventory else [0, 0, 0],
                "highest": specificity_inventory[:10],
                "limits": [0, MAX_CLASS_SPECIFICITY, MAX_TYPE_SPECIFICITY],
            },
            "rawGeometry": [
                {**item, "exceptionId": valid_exceptions.get(item["signature"], {}).get("id")} for item in raw_geometry
            ],
            "physicalDirectionalDeclarations": physical_direction,
            "exceptions": {
                "declared": len(valid_exceptions),
                "used": len(used_exceptions),
                "ids": sorted(valid_exceptions[signature]["id"] for signature in used_exceptions),
            },
        },
    }


def product_style_analysis(repo: Path) -> dict[str, Any]:
    try:
        sources = load_product_style_sources(repo)
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "errors": [f"[source-read] cannot load product style analysis inputs: {exc}"],
            "details": {},
        }
    return analyze_product_style_sources(*sources)


def product_style_errors(repo: Path) -> list[str]:
    return list(product_style_analysis(repo)["errors"])


CAPTURE_METADATA_KEYS = frozenset(
    {
        "caseId",
        "surfaceId",
        "stateId",
        "theme",
        "viewport",
        "role",
        "referencePage",
        "width",
        "height",
    }
)
Capture = Callable[[dict[str, Any], bytes], None]
CaptureRender = Callable[[Capture], tuple[list[str], dict[str, Any]]]


def _json_bytes(value: Any) -> bytes:
    # allow_nan=False rejects nonfinite geometry, including nested values.
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _canonical_capture_path(repo: Path, relative: str, *, exists: bool = True) -> Path:
    if any(part in {"", ".", ".."} for part in relative.split("/")):
        raise ValueError("capture path must have no aliases or traversal")
    return confined_path(repo, relative, must_exist=exists)


def _capture_contract(contract: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not contract:
        raise ValueError("capture contract must not be empty")
    result: dict[str, dict[str, Any]] = {}
    identities: set[tuple[str, str]] = set()
    for metadata in contract:
        if set(metadata) != CAPTURE_METADATA_KEYS:
            raise ValueError("capture metadata has unexpected or missing fields")
        for field in ("caseId", "surfaceId", "stateId", "referencePage"):
            if not isinstance(metadata[field], str) or not metadata[field].strip():
                raise ValueError(f"capture {field} must be nonempty text")
        if metadata["role"] not in {"product", "reference"} or metadata["theme"] not in {"light", "dark"}:
            raise ValueError("capture role or theme is invalid")
        dimensions = {field: metadata[field] for field in ("width", "height")}
        if any(type(value) is not int or not 1 <= value <= 4096 for value in dimensions.values()):
            raise ValueError("capture dimensions must be bounded positive integers")
        if metadata["viewport"] != dimensions:
            raise ValueError("capture dimensions must match the viewport screenshot policy")
        identity = (metadata["caseId"].casefold(), metadata["role"])
        if identity in identities:
            raise ValueError("capture contract contains duplicate case/role identity")
        identities.add(identity)
        filename = hashlib.sha256(_json_bytes(metadata)).hexdigest() + ".png"
        result[filename] = metadata
    return result


def png_dimensions(payload: bytes) -> tuple[int, int]:
    """Decode the bounded noninterlaced 8-bit RGB(A) PNG form emitted by Chromium.

    Check every chunk CRC, structure, decompression length and row filter; a
    header alone is not proof of a complete image. No image dependency is needed.
    """
    if len(payload) > 50_000_000 or not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("capture must be a bounded PNG")
    offset = 8
    compressed = bytearray()
    width = height = channels = 0
    idat_closed = ended = False
    while offset < len(payload):
        if offset + 12 > len(payload):
            raise ValueError("truncated PNG chunk")
        size = struct.unpack_from("!I", payload, offset)[0]
        kind = payload[offset + 4 : offset + 8]
        end = offset + 12 + size
        if end > len(payload):
            raise ValueError("truncated PNG payload")
        data = payload[offset + 8 : end - 4]
        if zlib.crc32(kind + data) != struct.unpack_from("!I", payload, end - 4)[0]:
            raise ValueError("PNG chunk checksum mismatch")
        if offset == 8 and kind != b"IHDR":
            raise ValueError("PNG must start with IHDR")
        if kind == b"IHDR":
            if offset != 8 or size != 13:
                raise ValueError("invalid PNG header")
            width, height, depth, color, compression, filtering, interlace = struct.unpack("!2I5B", data)
            if (
                not (1 <= width <= 4096 and 1 <= height <= 4096)
                or (depth, compression, filtering, interlace) != (8, 0, 0, 0)
                or color not in {2, 6}
            ):
                raise ValueError("unsupported PNG screenshot encoding or dimensions")
            channels = 3 if color == 2 else 4
        elif kind == b"IDAT":
            if idat_closed:
                raise ValueError("PNG IDAT chunks must be consecutive")
            compressed.extend(data)
        elif kind == b"IEND":
            if size or end != len(payload) or not compressed:
                raise ValueError("invalid PNG completion")
            ended = True
        elif not kind[:1].islower():
            raise ValueError("unexpected critical PNG chunk")
        if compressed and kind != b"IDAT":
            idat_closed = True
        offset = end
    if not ended:
        raise ValueError("PNG completion chunk is missing")
    stride = width * channels + 1
    expected = stride * height
    decoder = zlib.decompressobj()
    try:
        decoded = decoder.decompress(bytes(compressed), expected + 1)
    except zlib.error as exc:
        raise ValueError("invalid PNG compressed pixels") from exc
    if len(decoded) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError("PNG pixel payload does not match dimensions")
    if any(decoded[offset] > 4 for offset in range(0, expected, stride)):
        raise ValueError("PNG contains an invalid row filter")
    return width, height


def _git_bytes(repo: Path, *args: str) -> bytes:
    execution = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)
    if execution.returncode:
        raise ValueError(f"capture Git boundary failed: {' '.join(args[:2])}")
    return execution.stdout


def _full_commit(repo: Path, commit: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("capture delivery/producer requires an immutable full Git commit")
    if _git_bytes(repo, "rev-parse", f"{commit}^{{commit}}").decode().strip() != commit:
        raise ValueError("invalid capture commit")
    return commit


def write_capture_bundle(
    repo: Path,
    relative: str,
    contract: list[dict[str, Any]],
    snapshot: Callable[[], dict[str, Any]],
    render: CaptureRender,
) -> Path:
    """Publish once; incomplete runs remain unaccepted without a manifest.

    This is a structural round trip, not immutable evidence authentication. Only
    read_capture_bundle with an independently supplied delivery commit does that.
    """
    repo = repo.resolve(strict=True)
    expected = _capture_contract(contract)
    destination = _canonical_capture_path(repo, relative, exists=False)
    producer = snapshot()
    _json_bytes(producer)
    _full_commit(repo, producer["producerCommit"])
    parents = [repo, *reversed(list(destination.parent.parents))]
    parents = [path for path in parents if path == repo or repo in path.parents]
    parents.append(destination.parent)
    with ExitStack() as held:
        held.enter_context(windows_path_locks(parents, directories=True))
        parent_identity = path_identity(destination.parent)
        destination.mkdir(exist_ok=False)
        held.enter_context(windows_path_locks([destination], directories=True))
        directory_identity = path_identity(destination)
        captures: dict[str, dict[str, Any]] = {}

        def guard() -> None:
            if (
                _canonical_capture_path(repo, relative) != destination
                or path_identity(destination.parent) != parent_identity
                or path_identity(destination) != directory_identity
            ):
                raise ValueError("capture destination identity changed")

        def write_once(path: Path, payload: bytes) -> None:
            guard()
            with path.open("xb") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            held.enter_context(windows_path_locks([path], directories=False))
            guard()
            if stable_file_bytes(repo, path) != payload:
                raise ValueError("capture output changed during publication")

        def capture(metadata: dict[str, Any], payload: bytes) -> None:
            (filename,) = _capture_contract([metadata])
            if expected.get(filename) != metadata or filename in captures:
                raise ValueError("unexpected or duplicate capture")
            if png_dimensions(payload) != (metadata["width"], metadata["height"]):
                raise ValueError("PNG dimensions differ from capture contract")
            write_once(destination / filename, payload)
            captures[filename] = {**metadata, "file": filename, "sha256": hashlib.sha256(payload).hexdigest()}

        errors, report = render(capture)
        if errors:
            raise ValueError("capture geometry/interaction failed: " + "; ".join(errors))
        if set(captures) != set(expected):
            raise ValueError("capture inventory is incomplete")
        if snapshot() != producer:
            raise ValueError("capture producer changed during rendering")
        manifest = {
            "schemaVersion": "1.0",
            "documentType": "product-style-capture-bundle",
            "screenshotPolicy": "viewport",
            "producer": producer,
            "report": report,
            "captures": [captures[key] for key in sorted(captures)],
        }
        encoded = _json_bytes(manifest)
        guard()
        if {path.name for path in destination.iterdir()} != set(captures):
            raise ValueError("capture destination has unexpected files")
        for item in captures.values():
            if hashlib.sha256(stable_file_bytes(repo, destination / item["file"])).hexdigest() != item["sha256"]:
                raise ValueError("capture changed before completion")
        write_once(destination / "manifest.json", encoded)
    return destination / "manifest.json"


def read_capture_bundle(
    repo: Path,
    manifest_path: Path,
    delivery_commit: str,
    contract: list[dict[str, Any]],
) -> dict[str, Any]:
    """Authenticate exact retained bytes against an external immutable Git ID."""
    repo = repo.resolve(strict=True)
    manifest_path = _canonical_capture_path(repo, manifest_path.relative_to(repo).as_posix())
    directory = manifest_path.parent
    directories = [directory, *[path for path in directory.parents if path == repo or repo in path.parents]]
    with windows_path_locks(directories, directories=True):
        identity = path_identity(directory)
        paths = sorted(directory.iterdir())
        for path in paths:
            _canonical_capture_path(repo, path.relative_to(repo).as_posix())
            if not path.is_file():
                raise ValueError("capture directory must contain only regular files")
        with windows_path_locks(paths, directories=False):
            before = {path.name: hashlib.sha256(stable_file_bytes(repo, path)).hexdigest() for path in paths}
            result = _read_capture_bundle_locked(repo, manifest_path, delivery_commit, contract)
            after = {path.name: hashlib.sha256(stable_file_bytes(repo, path)).hexdigest() for path in paths}
            if before != after or sorted(directory.iterdir()) != paths or path_identity(directory) != identity:
                raise ValueError("capture bundle changed during verification")
            return result


def _read_capture_bundle_locked(
    repo: Path,
    manifest_path: Path,
    delivery_commit: str,
    contract: list[dict[str, Any]],
) -> dict[str, Any]:
    repo = repo.resolve(strict=True)
    delivery = _full_commit(repo, delivery_commit)
    relative = manifest_path.relative_to(repo).as_posix()
    manifest_path = _canonical_capture_path(repo, relative)
    payload = stable_file_bytes(repo, manifest_path)
    if payload != _git_bytes(repo, "cat-file", "blob", f"{delivery}:{relative}"):
        raise ValueError("capture manifest differs from immutable delivery")
    manifest = json.loads(payload)
    if not isinstance(manifest, dict) or set(manifest) != {
        "schemaVersion",
        "documentType",
        "screenshotPolicy",
        "producer",
        "report",
        "captures",
    }:
        raise ValueError("invalid capture manifest fields")
    if (manifest["schemaVersion"], manifest["documentType"], manifest["screenshotPolicy"]) != (
        "1.0",
        "product-style-capture-bundle",
        "viewport",
    ):
        raise ValueError("invalid capture manifest identity")
    _json_bytes(manifest)
    producer = _full_commit(repo, manifest["producer"]["producerCommit"])
    _git_bytes(repo, "merge-base", "--is-ancestor", producer, delivery)
    expected = _capture_contract(contract)
    captures = manifest["captures"]
    if not isinstance(captures, list) or len(captures) != len(expected):
        raise ValueError("capture manifest inventory is incomplete")
    names: set[str] = set()
    for capture in captures:
        if not isinstance(capture, dict) or set(capture) != CAPTURE_METADATA_KEYS | {"file", "sha256"}:
            raise ValueError("invalid capture entry")
        filename = capture["file"]
        metadata = {key: capture[key] for key in CAPTURE_METADATA_KEYS}
        if filename in names or expected.get(filename) != metadata:
            raise ValueError("capture contract identity or filename mismatch")
        names.add(filename)
        path = _canonical_capture_path(repo, f"{manifest_path.parent.relative_to(repo).as_posix()}/{filename}")
        png = stable_file_bytes(repo, path)
        if hashlib.sha256(png).hexdigest() != capture["sha256"] or png_dimensions(png) != (
            metadata["width"],
            metadata["height"],
        ):
            raise ValueError("capture PNG content or dimensions changed")
        if png != _git_bytes(repo, "cat-file", "blob", f"{delivery}:{path.relative_to(repo).as_posix()}"):
            raise ValueError("capture PNG differs from immutable delivery")
    if {path.name for path in manifest_path.parent.iterdir()} != names | {"manifest.json"}:
        raise ValueError("capture directory inventory differs from contract")
    prefix = manifest_path.parent.relative_to(repo).as_posix() + "/"
    tracked = _git_bytes(repo, "ls-tree", "-r", "--name-only", "-z", delivery, "--", prefix).decode().split("\0")
    if {name.removeprefix(prefix) for name in tracked if name} != names | {"manifest.json"}:
        raise ValueError("immutable delivery capture inventory differs from contract")
    return manifest


CAPTURE_SOURCE_ROOTS = (
    "design/ui-reference",
    "services/core-api/src",
    "packages/contracts",
    "tests/desktop/fixtures",
)
CAPTURE_SOURCE_FILES = (
    ".gitattributes",
    "tools/product_style_check.py",
    "tools/desktop_app_check.py",
    "tools/ui_conformance.py",
    "tools/ui_reference_check.py",
    "tools/build_manifest.py",
    "verification/desktop-ui.schema.json",
    "verification/product-style-exceptions.json",
    "pyproject.toml",
    "uv.lock",
)


def capture_source_identity(repo: Path, commit: str, files: dict[str, str]) -> dict[str, str]:
    """Bind a complete caller-derived inventory to tracked, unchanged Git input."""
    _full_commit(repo, commit)
    _git_bytes(repo, "merge-base", "--is-ancestor", commit, "HEAD")
    entries: dict[str, str] = {}
    for raw in _git_bytes(repo, "ls-tree", "-r", "-z", commit).split(b"\0"):
        if not raw:
            continue
        identity, path_bytes = raw.split(b"\t", 1)
        path = path_bytes.decode("utf-8")
        if path not in files:
            continue
        mode, kind, blob = identity.decode().split()
        if mode not in {"100644", "100755"} or kind != "blob":
            raise ValueError(f"capture producer input is not a regular tracked file: {path}")
        entries[path] = blob
    if set(entries) != set(files):
        raise ValueError("capture producer contains untracked or missing Git inputs")
    dirty = set(_git_bytes(repo, "diff", "--name-only", "-z", commit).decode().split("\0"))
    if dirty.intersection(files):
        raise ValueError("capture producer inputs differ from the immutable source commit")
    # Index stat flags can conceal changed files from git diff. Hash actual
    # paths through Git's checkout/clean rules, independently of those flags.
    ordered_paths = sorted(files)
    checked_paths = [confined_path(repo, relative) for relative in ordered_paths]
    with windows_path_locks(checked_paths, directories=False):
        actual = subprocess.run(
            ["git", "hash-object", "--stdin-paths"],
            cwd=repo,
            check=False,
            capture_output=True,
            input=("\n".join(json.dumps(relative) for relative in ordered_paths) + "\n").encode("utf-8"),
        )
        if actual.returncode or actual.stdout.decode().splitlines() != [entries[path] for path in ordered_paths]:
            raise ValueError("capture producer bytes do not authenticate to the immutable Git blobs")
    for relative, digest in files.items():
        if hashlib.sha256(stable_file_bytes(repo, confined_path(repo, relative))).hexdigest() != digest:
            raise ValueError("capture producer input changed during Git binding")
    return dict(sorted(entries.items()))


def capture_producer_snapshot(repo: Path, commit: str | None = None) -> dict[str, Any]:
    from desktop_app_check import PRODUCT_MANIFEST, product_build_errors
    from ui_conformance import load_context

    repo = repo.resolve(strict=True)
    commit = commit or _git_bytes(repo, "rev-parse", "HEAD").decode().strip()
    errors = product_build_errors(repo)
    if errors:
        raise ValueError("capture requires a valid product build: " + "; ".join(errors))
    context = load_context(repo)
    product = json.loads(stable_file_bytes(repo, confined_path(repo, PRODUCT_MANIFEST)))
    reference = json.loads(stable_file_bytes(repo, confined_path(repo, context.config["applicationManifestPath"])))
    files = dict(product["sourceFiles"])
    for root in CAPTURE_SOURCE_ROOTS:
        tracked = set(
            filter(
                None, _git_bytes(repo, "ls-tree", "-r", "--name-only", "-z", commit, "--", root).decode().split("\0")
            )
        )
        found: set[str] = set()
        for directory, child_directories, names in os.walk(confined_path(repo, root), followlinks=False):
            child_directories[:] = sorted(
                name for name in child_directories if name not in {"__pycache__", "node_modules", "dist"}
            )
            for name in [*child_directories, *names]:
                path = Path(directory) / name
                relative = path.relative_to(repo).as_posix()
                confined_path(repo, relative)
                if name in names:
                    found.add(relative)
                    files[relative] = hashlib.sha256(stable_file_bytes(repo, path)).hexdigest()
        if found != tracked:
            raise ValueError(f"capture producer root inventory differs from Git: {root}")
    for relative in CAPTURE_SOURCE_FILES:
        files[relative] = hashlib.sha256(stable_file_bytes(repo, confined_path(repo, relative))).hexdigest()
    blobs = capture_source_identity(repo, commit, files)
    return {
        "producerCommit": commit,
        "inputGitBlobs": blobs,
        "inputSha256": dict(sorted(files.items())),
        "productManifest": product,
        "referenceBuildManifest": reference,
        "referenceId": context.config["referenceId"],
        "referencePackageSha256": context.config["referencePackageSha256"],
        "rendererSettings": context.config["visual"],
    }


def qualify_product_captures(repo: Path, relative: str) -> Path:
    from desktop_app_check import product_style_qualification_matrix, qualification_capture_contract

    # Never label execution of one checkout's adapters as another's producer.
    if Path(__file__).resolve() != repo / "tools/product_style_check.py":
        raise ValueError("capture must execute the producer checkout's checker")
    static = product_style_analysis(repo)
    if not static["ok"]:
        raise ValueError("capture style analysis failed: " + "; ".join(static["errors"]))
    producer = capture_producer_snapshot(repo)
    paths = list(producer["inputSha256"])
    for root, manifest_key in (
        ("apps/desktop/product-dist", "productManifest"),
        ("apps/desktop/dist", "referenceBuildManifest"),
    ):
        paths.extend(f"{root}/{name}" for name in producer[manifest_key]["artifacts"])
        paths.append(f"{root}/application-manifest.json")
    with windows_path_locks([confined_path(repo, path) for path in paths], directories=False):
        if capture_producer_snapshot(repo) != producer:
            raise ValueError("producer changed before capture inputs were locked")
        return write_capture_bundle(
            repo,
            relative,
            qualification_capture_contract(repo),
            lambda: capture_producer_snapshot(repo),
            lambda capture: product_style_qualification_matrix(repo, capture),
        )


def verify_product_captures(repo: Path, relative: str, delivery: str) -> dict[str, Any]:
    from desktop_app_check import qualification_capture_contract, qualification_report_errors

    manifest = read_capture_bundle(
        repo, _canonical_capture_path(repo, relative), delivery, qualification_capture_contract(repo)
    )
    if manifest["producer"] != capture_producer_snapshot(repo, manifest["producer"]["producerCommit"]):
        raise ValueError("capture producer/build/reference/renderer identity differs from authenticated source")
    errors = qualification_report_errors(repo, manifest["report"])
    if errors:
        raise ValueError("retained capture matrix is invalid: " + "; ".join(errors))
    return {
        "ok": True,
        "deliveryCommit": delivery,
        "producerCommit": manifest["producer"]["producerCommit"],
        "manifest": relative,
        "captureCount": len(manifest["captures"]),
        "manifestSha256": hashlib.sha256(_git_bytes(repo, "cat-file", "blob", f"{delivery}:{relative}")).hexdigest(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--capture", help="new repository-relative directory for live product/reference captures")
    operation.add_argument("--verify-captures", help="repository-relative retained capture manifest")
    parser.add_argument("--delivery-commit", help="external full immutable Git commit authenticating retained files")
    args = parser.parse_args(argv)
    repo = args.repo.resolve(strict=True)
    try:
        if args.verify_captures:
            if not args.delivery_commit:
                raise ValueError("--verify-captures requires --delivery-commit")
            result = verify_product_captures(repo, args.verify_captures, args.delivery_commit)
        elif args.capture:
            if args.delivery_commit:
                raise ValueError("delivery authentication is available only after captures are committed")
            manifest = qualify_product_captures(repo, args.capture)
            result = {
                "ok": True,
                "manifest": manifest.relative_to(repo).as_posix(),
                "authentication": "structural-only; commit delivery then verify",
            }
        elif args.delivery_commit:
            raise ValueError("--delivery-commit requires --verify-captures")
        else:
            result = product_style_analysis(repo)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        result = {"ok": False, "errors": [str(exc)]}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
