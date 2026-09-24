"""First-party scientific mapping, not authentication, HTTP or scholarly truth.

Only the Core broker compiles these fixed destinations. External values remain
source assertions; candidates are suggestions and never mint canonical Work IDs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlencode, urlsplit

from ..ingestion.reference_imports import normalize_import_field
from .contracts import (
    CitationQuery,
    ConnectorCapabilities,
    ConnectorCursor,
    ConnectorRecord,
    ConnectorRequest,
    ErrorCode,
    LookupQuery,
    OaQuery,
    ProviderIdentifier,
    RecommendationQuery,
    SearchFilter,
    SearchQuery,
    SourceField,
    SourceTerms,
    _utc,
)

VERSION = "1.0.0"
HOSTS = {
    "openalex": "api.openalex.org",
    "crossref": "api.crossref.org",
    "unpaywall": "api.unpaywall.org",
    "semantic-scholar": "api.semanticscholar.org",
}
TERMS = {
    "openalex": "https://help.openalex.org/",
    "crossref": "https://www.crossref.org/documentation/retrieve-metadata/rest-api/",
    "unpaywall": "https://data.unpaywall.org/products/api",
    "semantic-scholar": "https://www.semanticscholar.org/product/api",
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
    method: str = "GET"
    body: bytes | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class MappedPage:
    records: tuple[ConnectorRecord, ...] = field(repr=False)
    next_cursor: ConnectorCursor | None = field(repr=False)
    terms: SourceTerms = field(repr=False)
    warnings: tuple[str, ...] = ()


def capabilities(provider: str) -> ConnectorCapabilities:
    if provider not in HOSTS:
        raise ProviderProblem("unsupported-operation")
    if provider in {"unpaywall", "semantic-scholar"}:
        oa = provider == "unpaywall"
        return ConnectorCapabilities(
            schema_version="1.0",
            provider_id=provider,
            adapter_version=VERSION,
            source_api_version="2" if oa else "1",
            operations=("oa-resolution",) if oa else ("citations", "lookup", "recommendations"),
            identifier_schemes=("doi",) if oa else ("doi", "semantic-scholar"),
            maximum_page_size=1 if oa else 500,
            configuration="ready",
            required_settings=("contact",) if oa else (),
        )
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
    if provider in {"unpaywall", "semantic-scholar"}:
        return _compile_graph_oa(request)
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
        elif provider in {"unpaywall", "semantic-scholar"}:
            oa = record.get("is_oa" if provider == "unpaywall" else "isOpenAccess")
            access = "open" if oa is True else "closed" if oa is False else "unknown"
            location = record.get("best_oa_location" if provider == "unpaywall" else "openAccessPdf")
            if location is not None:
                if not isinstance(location, dict):
                    raise ProviderProblem("incompatible-response")
                observed = location.get("license")
                if observed is not None and not isinstance(observed, str):
                    raise ProviderProblem("incompatible-response")
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
        if provider in {"unpaywall", "semantic-scholar"}:
            return _map_graph_oa(request, document, retrieved_at)
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


_GRAPH_FIELDS = "title,authors,year,publicationDate,venue,externalIds,isOpenAccess,openAccessPdf"
_MAX_OFFSET = 100_000_000


def _semantic_id(identifier: ProviderIdentifier) -> str:
    if identifier.scheme == "doi":
        return "DOI:" + doi(identifier.value)
    if identifier.scheme == "semantic-scholar" and re.fullmatch(r"[0-9a-fA-F]{40}", identifier.value):
        return identifier.value.lower()
    raise ProviderProblem("invalid-query")


def _offset(request: ConnectorRequest) -> int:
    if request.cursor is None:
        return 0
    value = request.cursor.value
    if re.fullmatch(r"[1-9][0-9]{0,8}", value) is None or int(value) > _MAX_OFFSET:
        raise ProviderProblem("invalid-cursor")
    return int(value)


def _compile_graph_oa(request: ConnectorRequest) -> WireQuery:
    provider, query = request.provider_id, request.query
    host = HOSTS[provider]
    if isinstance(query, OaQuery):
        if provider != "unpaywall" or request.cursor is not None:
            raise ProviderProblem("unsupported-operation")
        return WireQuery(host, "/v2/" + quote(doi(query.identifier.value), safe=""), (), True)
    if provider != "semantic-scholar":
        raise ProviderProblem("unsupported-operation")
    pairs = [("fields", _GRAPH_FIELDS)]
    if isinstance(query, LookupQuery):
        if len(query.identifiers) != 1 or request.cursor is not None:
            raise ProviderProblem("unsupported-operation")
        return WireQuery(
            host, "/graph/v1/paper/" + quote(_semantic_id(query.identifiers[0]), safe=""), tuple(pairs), True
        )
    if isinstance(query, CitationQuery):
        pairs.extend((("offset", str(_offset(request))), ("limit", str(request.page_size))))
        pairs[0] = ("fields", _GRAPH_FIELDS + ",contexts,intents,isInfluential")
        return WireQuery(
            host, "/graph/v1/paper/" + quote(_semantic_id(query.seed), safe="") + "/" + query.direction, tuple(pairs)
        )
    if isinstance(query, RecommendationQuery):
        if request.cursor is not None:
            raise ProviderProblem("unsupported-operation")
        positive = [_semantic_id(item) for item in query.positive_seeds]
        negative = [_semantic_id(item) for item in query.negative_seeds]
        if len(set(positive + negative)) != len(positive + negative):
            raise ProviderProblem("invalid-query")
        body = json.dumps({"positivePaperIds": positive, "negativePaperIds": negative}, separators=(",", ":")).encode()
        if len(body) > 128 * 1024:
            raise ProviderProblem("invalid-query")
        pairs.append(("limit", str(request.page_size)))
        return WireQuery(host, "/recommendations/v1/papers", tuple(pairs), False, "POST", body)
    raise ProviderProblem("unsupported-operation")


def _oa_locations(raw: dict[str, Any]) -> list[dict[str, Any]]:
    locations = raw.get("oa_locations")
    if not isinstance(locations, list):
        raise ProviderProblem("incompatible-response")
    for location in locations:
        if not isinstance(location, dict):
            raise ProviderProblem("incompatible-response")
        for name in ("url", "url_for_pdf", "url_for_landing_page", "host_type", "license", "version"):
            value = location.get(name)
            if value is not None and not isinstance(value, str):
                raise ProviderProblem("incompatible-response")
            if name.startswith("url") and value is not None:
                address = urlsplit(value)
                if (
                    address.scheme not in {"http", "https"}
                    or not address.netloc
                    or address.username
                    or address.password
                ):
                    raise ProviderProblem("incompatible-response")
                _safe(value)
    return locations


def _graph_record(
    raw: dict[str, Any], request: ConnectorRequest, retrieved_at: str, edge: dict | None = None
) -> ConnectorRecord:
    if not isinstance(raw, dict):
        raise ProviderProblem("incompatible-response")
    raw_id = ProviderIdentifier(scheme="semantic-scholar", value=raw["paperId"])
    identifiers = [ProviderIdentifier(scheme="semantic-scholar", value=_semantic_id(raw_id))]
    external = raw.get("externalIds")
    if external is not None:
        if not isinstance(external, dict):
            raise ProviderProblem("incompatible-response")
        if external.get("DOI"):
            identifiers.append(ProviderIdentifier(scheme="doi", value=doi(external["DOI"])))
    if raw.get("title") is not None and not isinstance(raw["title"], str):
        raise ProviderProblem("incompatible-response")
    if raw.get("authors") is not None and not isinstance(raw["authors"], list):
        raise ProviderProblem("incompatible-response")
    candidates = {
        "title": raw.get("title"),
        "authors": raw.get("authors"),
        "date": raw.get("publicationDate"),
        "venue": raw.get("venue"),
    }
    if isinstance(request.query, (CitationQuery, RecommendationQuery)):
        candidates["discovery"] = request.query.model_dump(mode="json", by_alias=True)
    source = dict(raw)
    if edge is not None:
        if "edge" in source:
            raise ProviderProblem("incompatible-response")
        source["edge"] = edge
    return ConnectorRecord(
        provider_id="semantic-scholar",
        raw_identifier=raw_id,
        identifiers=tuple(identifiers),
        retrieved_at=retrieved_at,
        fields=_source_fields("semantic-scholar", source, candidates),
        terms=source_terms("semantic-scholar", raw),
    )


def _map_graph_oa(request: ConnectorRequest, document: dict, retrieved_at: str) -> MappedPage:
    provider, query = request.provider_id, request.query
    if isinstance(query, OaQuery):
        identifier = ProviderIdentifier(scheme="doi", value=document["doi"])
        normalized = doi(identifier.value)
        if normalized != doi(query.identifier.value):
            raise ProviderProblem("incompatible-response")
        locations = _oa_locations(document)
        record = ConnectorRecord(
            provider_id=provider,
            raw_identifier=identifier,
            identifiers=(ProviderIdentifier(scheme="doi", value=normalized),),
            retrieved_at=retrieved_at,
            fields=_source_fields(provider, document, {"title": document.get("title"), "oa-locations": locations}),
            terms=source_terms(provider, document),
        )
        return MappedPage((record,), None, source_terms(provider))
    following = None
    records: tuple[ConnectorRecord, ...]
    if isinstance(query, LookupQuery):
        records = (_graph_record(document, request, retrieved_at),)
        expected = _semantic_id(query.identifiers[0])
        if expected not in {_semantic_id(item) for item in records[0].identifiers}:
            raise ProviderProblem("incompatible-response")
    elif isinstance(query, RecommendationQuery):
        values = document["recommendedPapers"]
        if not isinstance(values, list):
            raise ProviderProblem("incompatible-response")
        records = tuple(_graph_record(item, request, retrieved_at) for item in values)
    elif isinstance(query, CitationQuery):
        offset, values, continuation = document["offset"], document["data"], document.get("next")
        if type(offset) is not int or offset != _offset(request) or not isinstance(values, list):
            raise ProviderProblem("incompatible-response")
        key = "citingPaper" if query.direction == "citations" else "citedPaper"
        records = tuple(_graph_record(item[key], request, retrieved_at, item) for item in values)
        if continuation is not None:
            if type(continuation) is not int or not values or not offset < continuation <= _MAX_OFFSET:
                raise ProviderProblem("incompatible-response")
            following = ConnectorCursor(
                provider_id=provider,
                project_id=request.project_id,
                request_sha256=request.scientific_sha256(),
                page_index=request.cursor.page_index + 1 if request.cursor else 1,
                value=str(continuation),
                expires_at=None,
            )
    else:
        raise ProviderProblem("unsupported-operation")
    identities = {item.raw_identifier.value.lower() for item in records}
    if len(records) > request.page_size or len(identities) != len(records):
        raise ProviderProblem("incompatible-response")
    return MappedPage(
        records,
        following,
        source_terms(provider),
        ("non-snapshot-pagination",) if isinstance(query, CitationQuery) else (),
    )
