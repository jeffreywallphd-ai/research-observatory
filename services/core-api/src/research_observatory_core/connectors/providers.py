"""First-party scientific mapping, not authentication, HTTP or scholarly truth.

Only the Core broker compiles these fixed destinations. External values remain
source assertions; candidates are suggestions and never mint canonical Work IDs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlencode

from ..ingestion.reference_imports import normalize_import_field
from .contracts import (
    ConnectorCapabilities,
    ConnectorCursor,
    ConnectorRecord,
    ConnectorRequest,
    ErrorCode,
    LookupQuery,
    ProviderIdentifier,
    SearchFilter,
    SearchQuery,
    SourceField,
    SourceTerms,
    _utc,
)

VERSION = "1.0.0"
HOSTS = {"openalex": "api.openalex.org", "crossref": "api.crossref.org"}
TERMS = {
    "openalex": "https://help.openalex.org/",
    "crossref": "https://www.crossref.org/documentation/retrieve-metadata/rest-api/",
}


class ProviderProblem(ValueError):
    def __init__(self, code: ErrorCode):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class WireQuery:
    host: str
    path: str = field(repr=False)
    parameters: tuple[tuple[str, str], ...] = field(repr=False)
    singleton: bool = False


@dataclass(frozen=True, slots=True)
class MappedPage:
    records: tuple[ConnectorRecord, ...] = field(repr=False)
    next_cursor: ConnectorCursor | None = field(repr=False)
    terms: SourceTerms = field(repr=False)
    warnings: tuple[str, ...] = ()


def capabilities(provider: str) -> ConnectorCapabilities:
    if provider not in HOSTS:
        raise ProviderProblem("unsupported-operation")
    return ConnectorCapabilities(
        schema_version="1.0",
        provider_id=provider,
        adapter_version=VERSION,
        source_api_version=None,
        operations=("lookup", "search"),
        identifier_schemes=("doi", "openalex") if provider == "openalex" else ("doi",),
        maximum_page_size=100 if provider == "openalex" else 1000,
        configuration="ready",
        required_settings=(),
    )


def _safe(value: str, *, grammar: bool = False) -> str:
    if not value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ProviderProblem("invalid-query")
    if grammar and any(char in value for char in ",|!+"):
        raise ProviderProblem("unsupported-operation")
    return value


def doi(value: str) -> str:
    candidate = normalize_import_field("doi", value, 0, set())
    if candidate is None:
        raise ProviderProblem("invalid-query")
    return _safe(candidate.value)


def _alex_id(value: str, kind: str) -> str:
    value = value.removeprefix("https://openalex.org/")
    if re.fullmatch(kind + r"[1-9][0-9]{0,19}", value) is None:
        raise ProviderProblem("invalid-query")
    return value


def _filter(provider: str, item: SearchFilter) -> tuple[str, ...]:
    value = _safe(item.value, grammar=True)
    if item.field == "publication-year":
        if re.fullmatch(r"[1-9][0-9]{3}", value) is None:
            raise ProviderProblem("invalid-query")
        start, end = (
            ("from_publication_date", "to_publication_date")
            if provider == "openalex"
            else ("from-pub-date", "until-pub-date")
        )
        result = []
        if item.operator in {"gte", "eq"}:
            result.append(start + ":" + value + "-01-01")
        if item.operator in {"lte", "eq"}:
            result.append(end + ":" + value + "-12-31")
        return tuple(result)
    if item.operator != "eq":
        raise ProviderProblem("unsupported-operation")
    if item.field == "author-id":
        if provider == "openalex":
            return ("authorships.author.id:" + _alex_id(value, "A"),)
        value = value.removeprefix("https://orcid.org/")
        if re.fullmatch(r"[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]", value) is None:
            raise ProviderProblem("invalid-query")
        return ("orcid:" + value,)
    if item.field == "source-id":
        if provider == "openalex":
            return ("primary_location.source.id:" + _alex_id(value, "S"),)
        if re.fullmatch(r"[0-9]{4}-[0-9]{3}[0-9X]", value) is None:
            raise ProviderProblem("invalid-query")
        return ("issn:" + value,)
    if item.field == "work-type" and re.fullmatch(r"[a-z]+(?:-[a-z]+)*", value):
        return ("type:" + value,)
    if provider == "openalex":
        if item.field == "language" and re.fullmatch(r"[a-z]{2}", value):
            return ("language:" + value,)
        if item.field == "open-access" and value in {"true", "false"}:
            return ("open_access.is_oa:" + value,)
    raise ProviderProblem("unsupported-operation")


_PROJECTIONS = {
    "openalex": {
        "title": ("title",),
        "authors": ("authorships",),
        "date": ("publication_date", "publication_year"),
        "venue": ("primary_location",),
        "identifiers": ("ids", "doi"),
        "abstract": ("abstract_inverted_index",),
        "references": ("referenced_works",),
        "rights": ("primary_location", "open_access"),
    },
    "crossref": {
        "title": ("title",),
        "authors": ("author",),
        "date": ("published",),
        "venue": ("container-title",),
        "identifiers": ("DOI", "ISBN", "ISSN"),
        "abstract": ("abstract",),
        "references": ("reference",),
        "rights": ("license", "link"),
    },
}


def compile_request(request: ConnectorRequest) -> WireQuery:
    request = ConnectorRequest.model_validate(request)
    provider = request.provider_id
    try:
        capabilities(provider).assert_supported(request)
    except ValueError:
        raise ProviderProblem("unsupported-operation") from None
    query = request.query
    path, singleton = "/works", False
    pairs: list[tuple[str, str]] = []
    filters: list[str] = []
    if isinstance(query, LookupQuery):
        if provider == "crossref":
            if len(query.identifiers) != 1 or request.cursor is not None:
                raise ProviderProblem("unsupported-operation")
            path, singleton = "/works/" + quote(doi(query.identifiers[0].value), safe=""), True
        else:
            schemes = {item.scheme for item in query.identifiers}
            if len(schemes) != 1:
                raise ProviderProblem("unsupported-operation")
            scheme = query.identifiers[0].scheme
            values = [
                (
                    _safe("https://doi.org/" + doi(item.value), grammar=True)
                    if scheme == "doi"
                    else _alex_id(item.value, "W")
                )
                for item in query.identifiers
            ]
            if len(set(values)) != len(values):
                raise ProviderProblem("invalid-query")
            filters.append(scheme + ":" + "|".join(values))
    elif isinstance(query, SearchQuery):
        text = _safe(query.text, grammar=provider == "openalex" and query.field != "any")
        if provider == "openalex":
            if query.field == "any":
                pairs.append(("search", text))
            else:
                filters.append(query.field + ".search:" + text)
        elif query.field == "abstract":
            raise ProviderProblem("unsupported-operation")
        else:
            pairs.append(("query.title" if query.field == "title" else "query", text))
        for item in query.filters:
            filters.extend(_filter(provider, item))
        if query.sort:
            if provider == "crossref":
                if len(query.sort) != 1 or query.sort[0].field == "publication-date":
                    raise ProviderProblem("unsupported-operation")
                sort = query.sort[0]
                pairs.extend(
                    (
                        ("sort", "relevance" if sort.field == "relevance" else "is-referenced-by-count"),
                        ("order", "asc" if sort.direction == "ascending" else "desc"),
                    )
                )
            else:
                names = {
                    "relevance": "relevance_score",
                    "publication-date": "publication_date",
                    "citation-count": "cited_by_count",
                }
                pairs.append(
                    (
                        "sort",
                        ",".join(
                            names[item.field] + (":asc" if item.direction == "ascending" else ":desc")
                            for item in query.sort
                        ),
                    )
                )
        if query.fields:
            selection = ["id", "ids", "primary_location", "open_access"] if provider == "openalex" else ["DOI"]
            for name in query.fields:
                selection.extend(_PROJECTIONS[provider][name])
            if provider == "crossref":
                selection.append("license")
            pairs.append(("select", ",".join(dict.fromkeys(selection))))
    else:
        raise ProviderProblem("unsupported-operation")
    if filters:
        pairs.append(("filter", ",".join(filters)))
    if not singleton:
        pairs.extend(
            (
                ("per_page" if provider == "openalex" else "rows", str(request.page_size)),
                ("cursor", _safe(request.cursor.value) if request.cursor else "*"),
            )
        )
    result = WireQuery(HOSTS[provider], path, tuple(pairs), singleton)
    if len(("https://" + result.host + path + "?" + urlencode(pairs)).encode("ascii")) > 4000:
        raise ProviderProblem("invalid-query")
    return result


def source_terms(provider: str, record: dict[str, Any] | None = None) -> SourceTerms:
    observed = None
    access = "unknown"
    if record is not None:
        if provider == "openalex":
            location = record.get("primary_location") or {}
            observed = location.get("license")
            oa = record.get("open_access") or {}
            access = "open" if oa.get("is_oa") is True else "closed" if oa.get("is_oa") is False else "unknown"
        else:
            license_values = record.get("license")
            if license_values:
                observed = json.dumps(license_values, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    return SourceTerms.model_validate(
        {
            "license": {"state": "reported" if observed else "not-reported", "value": observed or None},
            "terms": {"state": "reported" if provider in TERMS else "unknown", "value": TERMS.get(provider)},
            "access": access,
        }
    )


def _source_fields(provider: str, raw: dict[str, Any], candidates: dict[str, Any]) -> tuple[SourceField, ...]:
    fields = []
    for name, value in raw.items():
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}", name) or name.startswith("candidate."):
            raise ProviderProblem("incompatible-response")
        fields.append(
            SourceField(
                namespace=provider,
                name=name,
                encoding="json",
                value=json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")),
            )
        )
    for name, value in candidates.items():
        if value is not None:
            fields.append(
                SourceField(
                    namespace=provider,
                    name="candidate." + name,
                    encoding="json",
                    value=json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")),
                )
            )
    return tuple(fields)


def _record(provider: str, raw: dict[str, Any], retrieved_at: str) -> ConnectorRecord:
    if not isinstance(raw, dict):
        raise ProviderProblem("incompatible-response")
    if provider == "openalex":
        raw_id = ProviderIdentifier(scheme="openalex", value=raw["id"])
        identifiers = [ProviderIdentifier(scheme="openalex", value=_alex_id(raw["id"], "W"))]
        if raw.get("doi"):
            identifiers.append(ProviderIdentifier(scheme="doi", value=doi(raw["doi"])))
        for name in ("authorships", "referenced_works"):
            if name in raw and not isinstance(raw[name], list):
                raise ProviderProblem("incompatible-response")
        title = raw.get("title")
        if title is not None and not isinstance(title, str):
            raise ProviderProblem("incompatible-response")
        candidates = {
            "title": title,
            "authors": raw.get("authorships"),
            "date": raw.get("publication_date"),
            "venue": (raw.get("primary_location") or {}).get("source"),
            "references": raw.get("referenced_works"),
        }
    else:
        raw_id = ProviderIdentifier(scheme="doi", value=raw["DOI"])
        identifiers = [ProviderIdentifier(scheme="doi", value=doi(raw["DOI"]))]
        for name in ("title", "author", "container-title", "reference", "license"):
            if name in raw and not isinstance(raw[name], list):
                raise ProviderProblem("incompatible-response")
        candidates = {
            "title": raw.get("title"),
            "authors": raw.get("author"),
            "date": raw.get("published"),
            "venue": raw.get("container-title"),
            "references": raw.get("reference"),
        }
    return ConnectorRecord(
        provider_id=provider,
        raw_identifier=raw_id,
        identifiers=tuple(identifiers),
        retrieved_at=retrieved_at,
        fields=_source_fields(provider, raw, candidates),
        terms=source_terms(provider, raw),
    )


def map_response(request: ConnectorRequest, document: object, *, retrieved_at: str) -> MappedPage:
    """Consume only bounded, broker-sanitized JSON; no partial success on drift."""
    plan = compile_request(request)
    _utc(retrieved_at)
    try:
        if not isinstance(document, dict):
            raise ValueError
        provider = request.provider_id
        if provider == "openalex":
            records = document["results"]
            cursor = document["meta"]["next_cursor"]
        elif document["status"] != "ok":
            raise ValueError
        elif plan.singleton:
            if document["message-type"] != "work":
                raise ValueError
            records, cursor = [document["message"]], None
        else:
            if document["message-type"] != "work-list":
                raise ValueError
            records = document["message"]["items"]
            cursor = document["message"].get("next-cursor")
            if isinstance(records, list) and len(records) < request.page_size:
                cursor = None
            elif cursor is None:
                raise ValueError
        if not isinstance(records, list) or len(records) > request.page_size:
            raise ValueError
        mapped = tuple(_record(provider, item, retrieved_at) for item in records)
        if isinstance(request.query, LookupQuery):
            expected = {
                (item.scheme, doi(item.value) if item.scheme == "doi" else _alex_id(item.value, "W"))
                for item in request.query.identifiers
            }
            if any(not expected.intersection((x.scheme, x.value) for x in item.identifiers) for item in mapped):
                raise ValueError
        identities = {(item.raw_identifier.scheme, item.raw_identifier.value.casefold()) for item in mapped}
        if len(identities) != len(mapped):
            raise ValueError
        following = None
        if cursor is not None:
            if not isinstance(cursor, str) or not cursor or (request.cursor and cursor == request.cursor.value):
                raise ValueError
            following = ConnectorCursor(
                provider_id=provider,
                project_id=request.project_id,
                request_sha256=request.scientific_sha256(),
                page_index=request.cursor.page_index + 1 if request.cursor else 1,
                value=cursor,
                expires_at=None,
            )
        warnings: tuple[str, ...] = (
            ("deprecated-field-search",)
            if provider == "openalex" and isinstance(request.query, SearchQuery) and request.query.field != "any"
            else ()
        )
        if provider == "crossref" and not plan.singleton:
            # The August 2026 cursor backend no longer promises snapshot isolation
            # or five-minute expiry. Never imply complete stable remote coverage.
            warnings += ("non-snapshot-pagination",)
        return MappedPage(mapped, following, source_terms(provider), warnings)
    except KeyError, IndexError, TypeError, ValueError, AttributeError, OverflowError:
        raise ProviderProblem("incompatible-response") from None
