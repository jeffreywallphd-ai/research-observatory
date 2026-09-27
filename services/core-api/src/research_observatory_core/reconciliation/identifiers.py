"""Versioned local normalization. Valid syntax is never registry verification.

Normative sources and conservative exclusions are documented in
packages/contracts/scholarly-records/README.md. No function performs I/O.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from typing import Annotated, Literal
from urllib.parse import unquote, urlsplit, urlunsplit

from pydantic import Field

from ..ingestion.import_drafts import DraftValue

NORMALIZER_VERSION: Literal["scholarly-identifiers/1.0.0"] = "scholarly-identifiers/1.0.0"
type IdentifierScope = Literal[
    "work", "work-version", "person", "organization", "container", "location", "heuristic", "unknown"
]
_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


class NormalizedIdentifier(DraftValue):
    normalizer_version: Literal["scholarly-identifiers/1.0.0"] = NORMALIZER_VERSION
    scheme: Annotated[str, Field(min_length=1, max_length=64)]
    observed: Annotated[str, Field(max_length=65536)] = Field(repr=False)
    canonical: Annotated[str, Field(min_length=1, max_length=65536)] | None = Field(repr=False)
    scope: IdentifierScope
    status: Literal["valid", "invalid", "unsupported"]
    issues: tuple[Literal["invalid-identifier", "unsupported-scheme"], ...]
    registry_verified: Literal[False] = False


def _ascii_lower(value: str) -> str:
    return value.translate(_ASCII_LOWER)


def _require(condition: bool) -> None:
    if not condition:
        raise ValueError("invalid-identifier")


def _positive_decimal(value: str) -> str:
    _require(re.fullmatch(r"[0-9]{1,32}", value) is not None and int(value) > 0)
    return str(int(value))


def _url_parts(value: str):
    # urlsplit silently strips controls, so validate before parsing. This is a
    # URI normalizer, not a URL fetcher or a claim that a location is safe to visit.
    _require(not any(char.isspace() or ord(char) < 32 or ord(char) > 126 for char in value))
    _require("\\" not in value and re.search(r"%(?![0-9a-fA-F]{2})", value) is None)
    parts = urlsplit(value)
    _require(parts.scheme in {"http", "https"} and bool(parts.hostname))
    _require(parts.username is None and parts.password is None and parts.port != 0)
    _require(re.fullmatch(r"[A-Za-z0-9.:[\]-]+", parts.netloc) is not None)
    return parts


def _resolver_path(value: str, hosts: set[str]) -> str:
    parts = _url_parts(value)
    _require(parts.hostname in hosts and parts.port in {None, 80 if parts.scheme == "http" else 443})
    _require("?" not in value and "#" not in value)
    return unquote(parts.path[1:], encoding="utf-8", errors="strict")


def _doi(value: str) -> tuple[str, IdentifierScope]:
    if _ascii_lower(value).startswith(("https://", "http://")):
        value = _resolver_path(value, {"doi.org", "dx.doi.org"})
    elif _ascii_lower(value).startswith("doi:"):
        value = value[4:].strip()
    _require(re.fullmatch(r"10\.[0-9]+(?:\.[0-9]+)*/.+", value) is not None)
    _require(all(unicodedata.category(char)[0] in "LMNPS" or unicodedata.category(char) == "Zs" for char in value))
    # Unicode casefold/NFC and trailing-punctuation removal change valid names.
    return _ascii_lower(value), "work"


def _pmid(value: str) -> tuple[str, IdentifierScope]:
    if _ascii_lower(value).startswith(("http://", "https://")):
        value = _resolver_path(value, {"pubmed.ncbi.nlm.nih.gov"}).removesuffix("/")
    elif _ascii_lower(value).startswith("pmid:"):
        value = value[5:].strip()
    return _positive_decimal(value), "work"


def _arxiv(value: str) -> tuple[str, IdentifierScope]:
    if _ascii_lower(value).startswith(("http://", "https://")):
        value = _resolver_path(value, {"arxiv.org", "www.arxiv.org", "export.arxiv.org"})
        _require(value.startswith(("abs/", "pdf/")))
        pdf = value.startswith("pdf/")
        value = value[4:]
        if pdf:
            value = value.removesuffix(".pdf")
    elif _ascii_lower(value).startswith("arxiv:"):
        value = value[6:].strip()
    modern = re.fullmatch(r"([0-9]{2})([0-9]{2})\.([0-9]{4,5})(v[1-9][0-9]{0,5})?", value)
    if modern is not None:
        year, month, sequence, version = modern.groups()
        date = int(year + month)
        _require(1 <= int(month) <= 12 and int(sequence) > 0)
        _require(date >= 704 and len(sequence) == (4 if date < 1501 else 5))
        return value, "work-version" if version else "work"
    old = re.fullmatch(r"([a-z][a-z-]+)(?:\.([A-Z]{2}))?/([0-9]{2})([0-9]{2})([0-9]{3})(v[1-9][0-9]{0,5})?", value)
    _require(old is not None)
    assert old is not None
    archive, classification, year, month, sequence, version = old.groups()
    # Archive spellings form part of the identifier, not a provider namespace.
    archives = {
        "acc-phys",
        "adap-org",
        "alg-geom",
        "ao-sci",
        "astro-ph",
        "atom-ph",
        "bayes-an",
        "chao-dyn",
        "chem-ph",
        "cmp-lg",
        "comp-gas",
        "cond-mat",
        "cs",
        "dg-ga",
        "funct-an",
        "gr-qc",
        "hep-ex",
        "hep-lat",
        "hep-ph",
        "hep-th",
        "math",
        "math-ph",
        "mtrl-th",
        "nlin",
        "nucl-ex",
        "nucl-th",
        "patt-sol",
        "physics",
        "plasm-ph",
        "q-alg",
        "q-bio",
        "quant-ph",
        "solv-int",
        "supr-con",
    }
    _require(archive in archives and (classification is None or archive in {"math", "cs", "nlin", "q-bio"}))
    date = int(year + month)
    _require(1 <= int(month) <= 12 and int(sequence) > 0 and (date >= 9107 or date <= 703))
    return f"{archive}/{year}{month}{sequence}{version or ''}", "work-version" if version else "work"


def _isbn(value: str) -> tuple[str, IdentifierScope]:
    value = re.sub(r"^ISBN(?:-1[03])?:?\s*", "", value, flags=re.ASCII | re.IGNORECASE)
    value = value.replace("-", "").replace(" ", "")
    if re.fullmatch(r"[0-9]{9}[0-9Xx]", value):
        digits = [int(char) if char not in "Xx" else 10 for char in value]
        _require(sum(digit * (10 - index) for index, digit in enumerate(digits)) % 11 == 0)
        prefix = "978" + value[:9]
        check = (-sum(int(char) * (1 if index % 2 == 0 else 3) for index, char in enumerate(prefix))) % 10
        value = prefix + str(check)
    _require(re.fullmatch(r"97[89][0-9]{10}", value) is not None)
    _require(sum(int(char) * (1 if index % 2 == 0 else 3) for index, char in enumerate(value)) % 10 == 0)
    return value, "work-version"


def _orcid(value: str) -> tuple[str, IdentifierScope]:
    if _ascii_lower(value).startswith(("http://", "https://")):
        value = _resolver_path(value, {"orcid.org"})
    value = value.replace("-", "")
    _require(re.fullmatch(r"[0-9]{15}[0-9Xx]", value) is not None)
    total = 0
    for digit in value[:15]:
        total = (total + int(digit)) * 2
    check = (12 - total % 11) % 11
    _require(value[-1].upper() == ("X" if check == 10 else str(check)))
    return "https://orcid.org/" + "-".join(value[index : index + 4].upper() for index in range(0, 16, 4)), "person"


def _openalex(value: str) -> tuple[str, IdentifierScope]:
    if _ascii_lower(value).startswith(("http://", "https://")):
        value = _resolver_path(value, {"openalex.org"})
    kinds: dict[str, tuple[str, IdentifierScope]] = {
        "W": ("works", "work"),
        "A": ("authors", "person"),
        "I": ("institutions", "organization"),
        "S": ("sources", "container"),
        "P": ("publishers", "organization"),
        "F": ("funders", "organization"),
    }
    namespace, _, short = value.rpartition("/")
    short = short.upper()
    _require(re.fullmatch(r"[WAISPF][1-9][0-9]{0,19}", short) is not None)
    plural, scope = kinds[short[0]]
    _require(not namespace or namespace.lower() == plural)
    return short, scope


def _s2_paper(value: str) -> tuple[str, IdentifierScope]:
    _require(re.fullmatch(r"[0-9a-fA-F]{40}", value) is not None)
    return value.lower(), "work"


def _s2_corpus(value: str) -> tuple[str, IdentifierScope]:
    if _ascii_lower(value).startswith("corpusid:"):
        value = value[9:]
    return _positive_decimal(value), "work"


def _percent(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        char = chr(int(match.group()[1:], 16))
        return char if char in _UNRESERVED else match.group().upper()

    return re.sub(r"%[0-9a-fA-F]{2}", replace, value)


def _url(value: str) -> tuple[str, IdentifierScope]:
    parts = _url_parts(value)
    netloc = parts.netloc.lower()
    if parts.port == (443 if parts.scheme == "https" else 80):
        netloc = netloc.rsplit(":", 1)[0]
    # Preserve empty query/fragment delimiters, path case and query ordering.
    result = urlunsplit(
        (parts.scheme, netloc, _percent(parts.path or "/"), _percent(parts.query), _percent(parts.fragment))
    )
    if "?" in value.split("#", 1)[0] and not parts.query:
        before, delimiter, after = result.partition("#")
        result = before + "?" + (delimiter + after if delimiter else "")
    if value.endswith("#"):
        result += "#"
    return result, "location"


def _title(value: str) -> tuple[str, IdentifierScope]:
    value = " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    _require(bool(value))
    return value, "heuristic"


_NORMALIZERS: dict[str, Callable[[str], tuple[str, IdentifierScope]]] = {
    "doi": _doi,
    "pmid": _pmid,
    "arxiv": _arxiv,
    "isbn": _isbn,
    "orcid": _orcid,
    "openalex": _openalex,
    "s2-paper": _s2_paper,
    "s2-corpus": _s2_corpus,
    "url": _url,
    "title": _title,
}


def normalize_identifier(scheme: str, observed: str) -> NormalizedIdentifier:
    if not isinstance(scheme, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", scheme):
        raise ValueError("identifier-scheme-invalid")
    if not isinstance(observed, str) or len(observed.encode("utf-8", errors="surrogatepass")) > 65536:
        raise ValueError("identifier-size-invalid")
    normalizer = _NORMALIZERS.get(scheme)
    canonical: str | None = None
    scope: IdentifierScope = "unknown"
    status: Literal["valid", "invalid", "unsupported"] = "unsupported"
    issues: tuple[Literal["invalid-identifier", "unsupported-scheme"], ...] = ("unsupported-scheme",)
    if normalizer is not None:
        try:
            _require(
                not any(
                    unicodedata.category(char).startswith("C") and not (scheme == "title" and char in "\t\r\n")
                    for char in observed
                )
            )
            # ADR-0027 treats literal boundary whitespace as presentation.
            # Resolver percent escapes are decoded afterward, so an explicitly
            # encoded suffix space remains part of the identifier.
            canonical, scope = normalizer(observed.strip())
            status, issues = "valid", ()
        except ValueError, UnicodeError:
            status, issues = "invalid", ("invalid-identifier",)
    return NormalizedIdentifier(
        scheme=scheme, observed=observed, canonical=canonical, scope=scope, status=status, issues=issues
    )
