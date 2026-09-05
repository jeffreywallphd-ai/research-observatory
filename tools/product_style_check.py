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
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    result = product_style_analysis(args.repo.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
